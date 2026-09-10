"""„Nadchádzajúce" — prehľad naplánovaných cronov (#527/#528 follow-up).

Čisto na čítanie: admin aj superadmin vidia, kedy najbližšie pobeží ktorá
naplánovaná úloha a čo presne urobí. Pri úlohách, ktoré posielajú push
notifikáciu, appka navyše predpočíta presný text správy (title + body) tou
istou logikou, akú pri odoslaní použije `api.tasks` — cez
`api.services.push_reminder_service`, aby text v prehľade nikdy nezišiel z
toho, čo sa naozaj pošle.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta

from django.utils import timezone
from rest_framework import viewsets
from rest_framework.response import Response

from .. import sections
from ..permissions import IsAdminOrAbove, SectionAccess

logger = logging.getLogger(__name__)

PUSH_DEADLINE_TASK = "api.tasks.send_push_deadline_reminder_task"
WEEKLY_REMINDER_TASK = "api.tasks.send_weekly_order_reminder_task"


def _push_deadline_preview(task, next_run):
    """Payload `send_push_deadline_reminder_task` pošle pri `next_run`."""
    from ..services import _next_workday
    from ..services.push_reminder_service import REMINDER_TITLE, build_reminder_body

    try:
        args = json.loads(task.args or "[]")
        meal_types = args[0] if args else []
    except (ValueError, IndexError, TypeError):
        return None
    if not meal_types or next_run is None:
        return None

    try:
        from ..cached_settings_service import get_global_settings

        gs = get_global_settings()
        is_day_before = getattr(gs, f"deadline_{meal_types[0]}_is_day_before", False)
    except Exception:
        is_day_before = False

    reference_date = timezone.localtime(next_run).date()
    target_date = _next_workday(reference_date) if is_day_before else reference_date
    return {
        "title": REMINDER_TITLE,
        "body": build_reminder_body(sorted(meal_types), target_date),
    }


def _weekly_reminder_preview(task, next_run):
    """Payload `send_weekly_order_reminder_task` pošle pri `next_run`."""
    from ..services.push_reminder_service import (
        REMINDER_TITLE,
        build_weekly_reminder_body,
    )

    if next_run is None:
        return None
    reference_date = timezone.localtime(next_run).date()
    return {
        "title": REMINDER_TITLE,
        "body": build_weekly_reminder_body(reference_date),
    }


_PUSH_PREVIEW_BUILDERS = {
    PUSH_DEADLINE_TASK: _push_deadline_preview,
    WEEKLY_REMINDER_TASK: _weekly_reminder_preview,
}


def _next_run_for_schedule(schedule, log_label):
    """Najbližší beh daného rozvrhu, alebo None ak sa nedá spočítať.

    Berie priamo `schedule` (celery `crontab`), nie `PeriodicTask` — vďaka
    tomu vie počítať aj pre syntetické uzávierky nižšie, ktoré v DB žiadny
    riadok nemajú (sú odvodené priamo z `GlobalSettings`, nie z vlastného cronu).
    """
    if schedule is None:
        return None
    now = timezone.now()
    try:
        # crontab.remaining_estimate() počíta hodinu/deň voči poľam crontabu,
        # ktoré sú v jeho vlastnej (lokálnej) tz — ale `maybe_make_aware`
        # vo vnútri je no-op pre už-aware datetime, takže aware `now` (UTC,
        # vďaka USE_TZ=True) sa porovnáva bez konverzie a výsledok je posunutý
        # o UTC↔lokálny offset. Rovnaký krok robí aj TzAwareCrontab.is_due()
        # (django_celery_beat), ktorý naozaj spúšťa Celery Beat — tu ho treba
        # zopakovať ručne, lebo remaining_estimate() sám o sebe to nerobí.
        schedule_tz = getattr(schedule, "tz", None)
        reference = now.astimezone(schedule_tz) if schedule_tz else now
        next_run = now + schedule.remaining_estimate(reference)
        # `remaining_estimate()` cieli pár mikrosekúnd PRED nastupujúcu minútu
        # (aby Celery Beat stihol spustiť presne na hranici) — bez tejto
        # korekcie admin v tabuľke videl čas o minútu skôr, než kedy úloha
        # naozaj pobeží (viď regresný test na `next_run`).
        return (next_run + timedelta(seconds=1)).replace(microsecond=0)
    except Exception:
        logger.warning("upcoming-events: remaining_estimate zlyhal pre %s", log_label)
        return None


def _next_run(periodic_task):
    """Najbližší beh naplánovanej úlohy, alebo None ak sa nedá spočítať."""
    return _next_run_for_schedule(periodic_task.schedule, periodic_task.name)


def _day_of_week_mask_for_days_before(days_before: int) -> str:
    """Cron `day_of_week` mask for a rule that fires `days_before` calendar
    days before a Mon–Fri target date (menu B/C deadline; #573).

    Targets are always weekdays (school meals aren't ordered for weekends),
    but the day it must fire on shifts with `days_before` and can land on a
    weekend itself (e.g. 2 days before Monday is Saturday) — unlike the
    breakfast/lunch/olovrant locks in `_deadline_lock_entries`, which only
    ever shift by 0 or 1 day (`api.signals._day_of_week`), this is calendar
    days, not business days — same arithmetic as the serializer check
    (`target_date - timedelta(days=deadline_menu_bc_days_before)`).
    """
    targets = (1, 2, 3, 4, 5)  # cron day_of_week: Mon–Fri
    days = sorted({(t - days_before) % 7 for t in targets})
    return ",".join(str(d) for d in days)


def _menu_bc_exempt_prevadzky_label() -> str:
    """Mená prevádzok s `menu_bc_same_deadline_as_lunch=True` — tie tento
    prísny termín vôbec nevidia, Menu B/C majú na bežnej uzávierke obeda
    (user 10.9.2026: piatkové Menu B pre deti bez narýchlo dokupovania)."""
    from ..models import Prevadzka

    names = list(
        Prevadzka.objects.filter(menu_bc_same_deadline_as_lunch=True)
        .order_by("nazov")
        .values_list("nazov", flat=True)
    )
    if not names:
        return ""
    return " Neplatí pre: " + ", ".join(names) + " (majú termín zhodný s Menu A)."


def _menu_bc_lock_entry(gs):
    """Syntetický riadok pre uzávierku navýšenia/nahlásenia Menu B a C —
    samostatná, prísnejšia než bežná uzávierka obeda (#573)."""
    from django.conf import settings

    try:
        from django_celery_beat.models import CrontabSchedule
    except ImportError:
        return None

    days_before = gs.deadline_menu_bc_days_before
    deadline = gs.deadline_menu_bc
    schedule = CrontabSchedule(
        minute=deadline.minute,
        hour=deadline.hour,
        day_of_week=_day_of_week_mask_for_days_before(days_before),
        day_of_month="*",
        month_of_year="*",
        timezone=settings.TIME_ZONE,
    )
    name = "order-lock-menu-bc-increase"
    return {
        "name": name,
        "task": "order-lock",
        "description": (
            f"Uzávierka navýšenia/nahlásenia Menu B a C: najneskôr "
            f"{days_before} dni vopred o {deadline.strftime('%H:%M')} "
            f"(kuchyňa ich dokupuje vopred). Odhlásenie/zníženie zostáva "
            f"možné podľa bežnej uzávierky obeda."
            f"{_menu_bc_exempt_prevadzky_label()}"
        ),
        "next_run": _next_run_for_schedule(schedule.schedule, name),
        "days": _days_label_sk(schedule.day_of_week),
    }


DAY_ABBR_SK = {0: "Ne", 1: "Po", 2: "Ut", 3: "St", 4: "Št", 5: "Pi", 6: "So"}


def _parse_day_of_week(day_of_week) -> set[int]:
    """Cron `day_of_week` string/int → set of day numbers (0=Ne … 6=So)."""
    dow = str(day_of_week).strip()
    if dow in ("*", ""):
        return set(range(7))
    days: set[int] = set()
    for part in dow.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s) % 7, int(end_s) % 7
            cur = start
            while True:
                days.add(cur)
                if cur == end:
                    break
                cur = (cur + 1) % 7
        else:
            days.add(int(part) % 7)
    return days


def _days_label_sk(day_of_week) -> str:
    """Human Slovak label for a cron `day_of_week` mask — "Po–Pi", "Ne–Št",
    "denne"… Ranges wrap around the week (e.g. menu B/C's "So–St", #573),
    since the mask isn't always Monday-anchored."""
    days = _parse_day_of_week(day_of_week)
    if not days or days == set(range(7)):
        return "denne"
    if len(days) == 1:
        return DAY_ABBR_SK[next(iter(days))]
    n = len(days)
    for start in sorted(days):
        seq = [(start + i) % 7 for i in range(n)]
        if set(seq) == days:
            return f"{DAY_ABBR_SK[seq[0]]}–{DAY_ABBR_SK[seq[-1]]}"
    # Not a single contiguous block — list it out rather than mislabel it.
    return ", ".join(DAY_ABBR_SK[d] for d in sorted(days, key=lambda d: (d - 1) % 7))


def _deadline_lock_entries():
    """Syntetické riadky uzávierky objednávok — kedy appka prestane prijímať
    zmeny pre raňajky/obed/olovrant (#548).

    Toto NIE JE cron: appka uzávierku vynucuje priebežne pri každej požiadavke
    porovnaním s `GlobalSettings.deadline_*`, žiadna úloha ju "nespustí". Admin
    v "Nadchádzajúcich" ale dovtedy videl len push pripomienku PRED uzávierkou
    (`send_push_deadline_reminder_task`), nie moment uzávierky samotnej — preto
    sa tu z tých istých polí dopočíta rovnako, ako to pre pripomienku aj
    auto-objednávku robí `api.signals` (rovnaké zoskupenie podľa zhodného času
    a `is_day_before`, rovnaká maska dní).
    """
    from django.conf import settings

    try:
        from django_celery_beat.models import CrontabSchedule
    except ImportError:
        return []

    from ..cached_settings_service import get_global_settings
    from ..signals import _day_of_week, _group_meals_by_deadline, _meal_types_label_sk

    try:
        gs = get_global_settings()
    except Exception:
        return []

    entries = []
    for (deadline, is_day_before), meal_types in _group_meals_by_deadline(gs).items():
        meal_types = sorted(meal_types)
        # Neuložený riadok — táto uzávierka nemá vlastnú DB úlohu, počíta sa
        # len na zobrazenie, nemá zmysel ju ukladať.
        schedule = CrontabSchedule(
            minute=deadline.minute,
            hour=deadline.hour,
            day_of_week=_day_of_week(is_day_before),
            day_of_month="*",
            month_of_year="*",
            timezone=settings.TIME_ZONE,
        )
        name = "order-lock-" + "-".join(meal_types)
        entries.append(
            {
                "name": name,
                "task": "order-lock",
                "description": (
                    f"Uzávierka objednávok ({_meal_types_label_sk(meal_types)}): "
                    f"appka odteraz odmietne zmeny objednávky na tento deň "
                    f"(uzávierka: {deadline.strftime('%H:%M')})."
                ),
                "next_run": _next_run_for_schedule(schedule.schedule, name),
                "days": _days_label_sk(schedule.day_of_week),
            }
        )

    menu_bc_entry = _menu_bc_lock_entry(gs)
    if menu_bc_entry is not None:
        entries.append(menu_bc_entry)

    return entries


class AdminUpcomingEventsViewSet(viewsets.ViewSet):
    """GET /api/admin/upcoming-events/ — zoradený zoznam naplánovaných cronov."""

    permission_classes = [IsAdminOrAbove, SectionAccess]
    section = sections.NADCHADZAJUCE

    def list(self, request):
        try:
            from django_celery_beat.models import PeriodicTask
        except ImportError:
            return Response({"results": []})

        tasks = (
            PeriodicTask.objects.filter(enabled=True)
            .select_related("crontab", "interval", "solar")
            .order_by("name")
        )

        results = []
        for task in tasks:
            next_run = _next_run(task)
            entry = {
                "name": task.name,
                "task": task.task,
                "description": task.description or "",
                "next_run": next_run,
                "days": (
                    _days_label_sk(task.crontab.day_of_week) if task.crontab else None
                ),
            }
            preview_builder = _PUSH_PREVIEW_BUILDERS.get(task.task)
            if preview_builder is not None:
                entry["push_preview"] = preview_builder(task, next_run)
            results.append(entry)

        # Zámerne bez zoradenia podľa next_run (#573 follow-up) — appka to
        # predtým zoraďovala podľa najbližšieho behu, takže sa poradie kariet
        # menilo priebežne s časom. Uzávierky (bez vlastného cronu) idú prvé,
        # zvyšné úlohy podľa mena — frontend si to ešte prezoskupí po kategórii.
        results = _deadline_lock_entries() + results
        return Response({"results": results})
