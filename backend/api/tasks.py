"""
Celery tasks for the api app.
"""

import logging
import time

from celery import shared_task
from django.conf import settings
from django.db import DatabaseError
from django.utils import timezone

from api.roles import klient_q
from api.services.push_notification_service import PushNotificationService

logger = logging.getLogger(__name__)

# Spreads push-reminder delivery across batches instead of sending to every
# subscriber in one instant. A single "uzávierka o chvíľu" push to everyone
# tends to make everyone open the app and log in within the same few
# seconds — measured load testing showed the backend collapses at roughly
# 4x its comfortable sustained rate (load-tests/README.md "Measured
# Capacity"), so a genuine simultaneous-open burst can realistically hit
# that. 0 by default (dev/test): only set via env in staging/prod settings.
#
# Batch size scales with recipient count (capped at PUSH_REMINDER_MAX_BATCHES
# batches) rather than using a fixed size, so total stagger time stays
# bounded regardless of how many users are subscribed —
# send_weekly_order_reminder_task has a 290s soft time limit.
PUSH_REMINDER_MIN_BATCH_SIZE = 25
PUSH_REMINDER_MAX_BATCHES = 10


def _log_cron_skip_event(task_name: str, reason: str, day) -> None:
    """Record a CRON_SKIPPED EventLog entry for an automatic run that was
    skipped for `reason` ("weekend" or "configured_day_off", per #442)."""
    from api.models import EventLog
    from api.services.event_log_service import log_event

    log_event(
        EventLog.EventType.CRON_SKIPPED,
        actor_label="cron",
        summary=f"{task_name}: preskočené ({reason}) na {day.isoformat()}.",
        payload={"reason": reason, "date": day.isoformat(), "task": task_name},
    )
    logger.info("%s skipped: reason=%s date=%s", task_name, reason, day)


def _log_cron_run(task_name: str, summary: str, payload: dict) -> None:
    """Zapíš, že cron úloha dobehla — aj keď nič neurobila.

    Preskočené behy sa zapisovali (`_log_cron_skip_event`), tie úspešné nie, takže
    v Udalostiach sa nedalo overiť, či scrape či report vôbec bežal — muselo sa
    liezť do logov `celery` kontajnera, kde ich prvý reštart prepíše. Ticho v
    audite navyše vyzerá rovnako ako výpadok.
    """
    from api.models import EventLog
    from api.services.event_log_service import log_event

    log_event(
        EventLog.EventType.CRON_RUN,
        actor_label="cron",
        summary=summary,
        payload={"task": task_name, **payload},
    )


def _log_cron_failure(task_name: str, exc: BaseException, payload: dict) -> None:
    """Zapíš pád cron úlohy. Bez toho po sebe zlyhanie nenechá stopu v audite."""
    from api.models import EventLog
    from api.services.event_log_service import log_event

    log_event(
        EventLog.EventType.CRON_FAILED,
        actor_label="cron",
        summary=f"{task_name}: zlyhalo — {type(exc).__name__}: {exc}".strip(),
        payload={"task": task_name, "error": f"{type(exc).__name__}: {exc}", **payload},
    )


def _cron_skip_check(task_name: str, check_date=None) -> str | None:
    """If `check_date` is a weekend or a configured Holiday, log the skip
    (see `_log_cron_skip_event`) and return the reason so the caller can
    bail out before any side effects. Returns None when the run should
    proceed normally.

    `check_date` must be the date the run actually prepares data FOR, not
    necessarily the date the cron fires on — a Sun-Thu evening schedule
    preparing tomorrow's (Mon-Fri) deadline must not skip just because
    today, the day it fires, happens to be a weekend (caught in prod on
    2026-08-31: the Sunday-evening leg of `apply_auto_orders_task` /
    `scrape_edupage_orders_task` silently skipped every week because this
    checked `timezone.localdate()` unconditionally instead of the resolved
    target date). Defaults to today for callers with no day-before target.

    Only call this for the Celery-Beat-scheduled path of a task (i.e. when
    no explicit target date was passed in) — a manually-triggered run for
    an explicit date is a deliberate admin action, not an automatic cron
    run, and must not be silently skipped.
    """
    from api.scheduling import cron_skip_reason

    day = check_date or timezone.localdate()
    reason = cron_skip_reason(day)
    if reason is None:
        return None
    _log_cron_skip_event(task_name, reason, day)
    return reason


def _push_batch_stagger_seconds() -> float:
    return getattr(settings, "PUSH_REMINDER_BATCH_STAGGER_SECONDS", 0)


def _push_batch_size(total_recipients: int) -> int:
    if total_recipients <= 0:
        return PUSH_REMINDER_MIN_BATCH_SIZE
    return max(
        PUSH_REMINDER_MIN_BATCH_SIZE,
        -(-total_recipients // PUSH_REMINDER_MAX_BATCHES),  # ceil division
    )


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="api.tasks.send_push_deadline_reminder_task",
)
def send_push_deadline_reminder_task(self, meal_types: list[str]):
    """
    Send push notifications to all subscribed clients 30 minutes before
    a meal deadline. When multiple meals share the same deadline they are
    passed together so that users receive a single combined notification.

    Args:
        meal_types: list of meal types, each one of 'breakfast', 'lunch',
                    'olovrant'. Meals that share a deadline are grouped
                    and sent as one notification.

    Target date logic:
    - If the is_day_before flag is set for a meal → target_date = next workday
    - Otherwise → target_date = today
    """
    from api.models import GlobalSettings, PushSubscription
    from api.services import _next_workday

    # Backward-compat: older Beat tasks stored args=["lunch"] (a bare string).
    # Iterating over a string would treat each character as a meal type and
    # return invalid_meal_type. Normalise to a list so old schedules keep
    # working until they are resynced by _sync_push_reminder_schedule.
    if isinstance(meal_types, str):
        meal_types = [meal_types]

    if not meal_types:
        logger.error("send_push_deadline_reminder_task: empty meal_types, no retry")
        return {"error": "empty_meal_types", "meal_types": meal_types}

    valid_meal_types = {"breakfast", "lunch", "olovrant"}
    invalid = [m for m in meal_types if m not in valid_meal_types]
    if invalid:
        logger.error(
            "send_push_deadline_reminder_task: invalid meal_types=%s, no retry",
            invalid,
        )
        return {"error": "invalid_meal_type", "meal_types": meal_types}

    try:
        gs = GlobalSettings.objects.get(pk=1)
    except GlobalSettings.DoesNotExist:
        logger.error(
            "send_push_deadline_reminder_task: GlobalSettings(pk=1) missing, no retry"
        )
        return {"error": "missing_global_settings", "meal_types": meal_types}

    from api.scheduling import day_off_reason, is_day_off

    today = timezone.localdate()

    # Determine target_date per meal and group by date.
    # All meals in one invocation typically share the same is_day_before, but
    # we handle them individually so settings changes mid-flight are safe.
    date_to_meals: dict = {}
    for meal_type in meal_types:
        is_day_before = getattr(gs, f"deadline_{meal_type}_is_day_before", False)
        target_date = _next_workday(today) if is_day_before else today
        # Skip weekends and admin-configured days off (Holiday) — #442.
        if not is_day_off(target_date):
            date_to_meals.setdefault(target_date, []).append(meal_type)

    if not date_to_meals:
        reason = day_off_reason(today) or "configured_day_off"
        logger.info(
            "send_push_deadline_reminder_task: %s skip for meal_types=%s",
            reason,
            meal_types,
        )
        _log_cron_skip_event("send_push_deadline_reminder_task", reason, today)
        return {"skipped": reason, "meal_types": meal_types}

    from api.services.push_reminder_service import build_reminder_body

    total_sent = 0
    sent_per_date: dict[str, int] = {}
    try:
        subscribed_user_ids = list(
            # Klientske notifikácie na objednávanie — kuchyňa ich dostávať nesmie,
            # hoci má tiež `is_staff=False` (#482).
            PushSubscription.objects.filter(
                klient_q("user"),
                user__is_active=True,
            )
            .values_list("user_id", flat=True)
            .distinct()
        )

        for target_date, date_meals in date_to_meals.items():
            body = build_reminder_body(date_meals, target_date)
            date_sent = 0
            stagger = _push_batch_stagger_seconds()
            batch_size = _push_batch_size(len(subscribed_user_ids))
            for idx, user_id in enumerate(subscribed_user_ids):
                if stagger and idx and idx % batch_size == 0:
                    time.sleep(stagger)
                result = PushNotificationService.send_to_user(
                    user_id=user_id,
                    title="Pripomienka objednávky",
                    body=body,
                    url="/order",
                )
                date_sent += result.get("sent", 0)
            total_sent += date_sent
            sent_per_date[str(target_date)] = date_sent
            logger.info(
                "send_push_deadline_reminder_task: meals=%s date=%s sent=%d",
                sorted(date_meals),
                target_date,
                date_sent,
            )

    except DatabaseError as exc:
        logger.exception(
            "send_push_deadline_reminder_task: database error, retrying..."
        )
        _log_cron_failure(
            "send_push_deadline_reminder_task", exc, {"meal_types": meal_types}
        )
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception(
            "send_push_deadline_reminder_task failed with non-transient error, no retry"
        )
        _log_cron_failure(
            "send_push_deadline_reminder_task", exc, {"meal_types": meal_types}
        )
        raise

    # "date" keeps the first date for backward compatibility with callers that
    # only expect a single date (the common case where all meals share one deadline).
    first_date = next(iter(date_to_meals))
    _log_cron_run(
        "send_push_deadline_reminder_task",
        f"Cron poslal {total_sent} push pripomienok "
        f"({', '.join(meal_types)}) na {first_date}.",
        {
            "sent": total_sent,
            "meal_types": meal_types,
            "date": str(first_date),
            "sent_per_date": {str(k): v for k, v in sent_per_date.items()},
        },
    )
    return {
        "sent": total_sent,
        "meal_types": meal_types,
        "date": str(first_date),
        "sent_per_date": sent_per_date,
    }


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    time_limit=300,
    soft_time_limit=290,
    name="api.tasks.send_weekly_order_reminder_task",
)
def send_weekly_order_reminder_task(self):
    """
    Send a Sunday push reminder to clients who have no submitted orders for next week.
    Fires every Sunday (scheduled via Celery Beat).
    Users who already have at least one submitted order for Mon–Fri of next week are skipped.
    """
    from django.db.models import Q

    from api.models import DailyOrder, PushSubscription
    from api.services.push_reminder_service import (
        build_weekly_reminder_body,
        next_week_range,
    )

    today = timezone.localdate()
    next_monday, next_friday = next_week_range(today)

    try:
        subscribed_user_ids = set(
            # Klientske notifikácie na objednávanie — kuchyňa ich dostávať nesmie,
            # hoci má tiež `is_staff=False` (#482).
            PushSubscription.objects.filter(
                klient_q("user"),
                user__is_active=True,
            )
            .values_list("user_id", flat=True)
            .distinct()
        )

        # Stored orders are submitted orders; draft requests delete the row.
        already_ordered = set(
            DailyOrder.objects.filter(
                user_id__in=subscribed_user_ids,
                date__range=(next_monday, next_friday),
            )
            .exclude(Q(data={}) | Q(data__isnull=True))
            .values_list("user_id", flat=True)
            .distinct()
        )

        recipients = subscribed_user_ids - already_ordered
        if not recipients:
            logger.info(
                "send_weekly_order_reminder_task: all users already ordered, skip"
            )
            _log_cron_run(
                "send_weekly_order_reminder_task",
                f"Cron: týždenná pripomienka na {next_monday} neposlaná — "
                "všetci už objednali.",
                {
                    "sent": 0,
                    "skipped_ordered": len(already_ordered),
                    "next_week": str(next_monday),
                },
            )
            return {"skipped": "all_ordered", "next_week": str(next_monday)}

        body = build_weekly_reminder_body(today)

        sent = 0
        stagger = _push_batch_stagger_seconds()
        batch_size = _push_batch_size(len(recipients))
        for idx, user_id in enumerate(recipients):
            if stagger and idx and idx % batch_size == 0:
                time.sleep(stagger)
            result = PushNotificationService.send_to_user(
                user_id=user_id,
                title="Pripomienka objednávky",
                body=body,
                url="/order",
            )
            sent += result.get("sent", 0)

        logger.info(
            "send_weekly_order_reminder_task: next_week=%s sent=%d skipped=%d",
            next_monday,
            sent,
            len(already_ordered),
        )
        _log_cron_run(
            "send_weekly_order_reminder_task",
            f"Cron poslal {sent} týždenných pripomienok na {next_monday}.",
            {
                "sent": sent,
                "skipped_ordered": len(already_ordered),
                "next_week": str(next_monday),
            },
        )
        return {
            "sent": sent,
            "skipped_ordered": len(already_ordered),
            "next_week": str(next_monday),
        }

    except DatabaseError as exc:
        logger.exception("send_weekly_order_reminder_task: database error, retrying...")
        _log_cron_failure(
            "send_weekly_order_reminder_task", exc, {"next_week": str(next_monday)}
        )
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception(
            "send_weekly_order_reminder_task: non-transient error, no retry"
        )
        _log_cron_failure(
            "send_weekly_order_reminder_task", exc, {"next_week": str(next_monday)}
        )
        raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def apply_auto_orders_task(
    self,
    date_str: str | None = None,
    meal_types: list[str] | None = None,
    same_day: bool = False,
):
    """
    Celery task: apply auto-orders for all eligible clients.
    Called by Celery Beat after the daily deadline.
    Can also be triggered manually via the admin API endpoint.

    `meal_types` obmedzí beh na tieto jedlá (#548) — raňajky a obed/olovrant
    majú inú uzávierku, preto ich Celery Beat spúšťa v dvoch samostatných
    crontaboch (viď `api.signals._sync_auto_order_schedule`), každý s vlastnou
    podmnožinou. `None` (napr. ručné spustenie z admina) naplní všetky jedlá
    naraz — viď `apply_auto_orders`.

    `same_day` hovorí, KTORÝ deň sa dnešný beh vzťahuje — pri deadline "deň
    vopred" (raňajky, beží večer) je to zajtrajší pracovný deň (`False`,
    pôvodné správanie); pri deadline "v deň podávania" (obed/olovrant, beží
    ráno) je to dnešok, ktorého uzávierka práve pominula (`True`). Ignoruje sa,
    keď je zadaný explicitný `date_str`.
    """
    try:
        import datetime

        from api.cache_service import clear_gramage_dashboard_cache
        from api.models import EventLog
        from api.services import apply_auto_orders
        from api.services.event_log_service import log_event

        task_label = (
            f"apply_auto_orders_task[{','.join(sorted(meal_types))}]"
            if meal_types
            else "apply_auto_orders_task"
        )

        target_date = None
        if date_str:
            target_date = datetime.date.fromisoformat(date_str)
        elif same_day:
            # Deadline "v deň podávania" (napr. obed/olovrant o 7:35) práve
            # pominul — dopĺňaj dnešok, nie zajtrajšok.
            target_date = timezone.localdate()
            if (reason := _cron_skip_check(task_label, target_date)) is not None:
                return {"skipped": True, "reason": reason}
        else:
            from api.services import _next_workday

            # Check the day this run actually prepares (the next workday),
            # not "today" — the Sun-Thu schedule fires on Sunday precisely
            # to prepare Monday, and Sunday itself is always a weekend.
            next_workday = _next_workday(timezone.localdate())
            if (reason := _cron_skip_check(task_label, next_workday)) is not None:
                return {"skipped": True, "reason": reason}

        result = apply_auto_orders(target_date, meal_types=meal_types)
        # Deadline práve pridal auto-objednávky — gramage dashboard by ich
        # ešte 5 minút neukazoval, keby cache ostala z pred deadline.
        clear_gramage_dashboard_cache(result["date"])
        log_event(
            EventLog.EventType.AUTO_ORDER_RUN,
            actor_label="cron",
            summary=f"Cron spustil auto-objednávky na {result['date']} ({task_label}).",
            payload={
                "created_count": len(result["created"]),
                "skipped_count": result["skipped"],
                "date": result["date"],
                "meal_types": meal_types,
            },
        )
        logger.info("%s result: %s", task_label, result)
        return result
    except Exception as exc:
        logger.exception("apply_auto_orders_task failed, retrying...")
        raise self.retry(exc=exc)


def _filter_order_data_by_meals(order_data, meal_types):
    if meal_types is None:
        return order_data
    return {
        meal_type: order_data[meal_type]
        for meal_type in meal_types
        if order_data.get(meal_type)
    }


_ALL_MEALS = ("breakfast", "lunch", "olovrant")
# Jedlá mimo deadline-riadeného toku (GlobalSettings deadliny, klientský výber,
# auto-order) — dnes len British `desiata` (#British Cluster C): počíta sa
# kusovo, rovnaká pre všetkých, žiadny vlastný deadline/porcia rozpad. NIE
# "snack" — ten string je už obsadený ako legacy alias pre Olovrant
# (`MealCategory.choices`, `ORDER_MEAL_TO_PLAN_MEALS` v `meal_plan_service.py`,
# `gramage_dashboard_export.meal_hue`) — pod tým menom by sa British desiata
# ticho zliala do olovrantovej gramáže. `_apply_scrape` tieto kľúče
# synchronizuje VŽDY (nie len keď sú v `requested_meals`), lebo British
# dedikovaný scrape aj hodinový preview beh čítajú z toho istého HTML fetchu
# ako lunch/breakfast/olovrant — bez tohto by sa "desiata" z `imported_data`
# ticho zahodila, keďže nikdy nie je v `_ALL_MEALS`.
_EXTRA_MEAL_KEYS = ("desiata",)

# Menu B/C majú u niektorých škôl skoršiu EduPage uzávierku než zvyšok obeda —
# kuchyňa chce ich odhad vidieť pár dní vopred (user 2.9.2026). Hardcoded zámerne:
# "toto zatiaľ môže byť hardcodnuté a napojené na obedový scrape".
PARTIAL_LUNCH_MEAL = "lunch"
PARTIAL_LUNCH_MENU_LETTERS = ("B", "C")
PARTIAL_LUNCH_DAYS_AHEAD = (1, 2)


def _meal_scrape_deadline_passed(gs, meal_type: str, target_date, now_local) -> bool:
    """True keď už prebehol (alebo mal prebehnúť) autoritatívny EduPage scrape
    pre ``meal_type`` na ``target_date``.

    Používa hodinový preview beh (``days_ahead``), aby po autoritatívnom
    scrape dané jedlo/deň znova neprepísal — inak by zmazal prípadnú ručnú
    admin opravu spravenú medzitým (2026-09-03: 08:00 preview beh takto
    prepísal 2 admin zásahy spravené po 7:35 lunch/olovrant deadline scrape,
    keď admin považoval 7:35 za posledný beh dňa).
    """
    import datetime

    sched_time, is_day_before = gs.edupage_scrape_schedule_for(meal_type)
    schedule_date = (
        target_date - datetime.timedelta(days=1) if is_day_before else target_date
    )
    deadline_dt = timezone.make_aware(
        datetime.datetime.combine(schedule_date, sched_time)
    )
    return now_local >= deadline_dt


def _log_scrape_order_event(order, previous_data: dict, is_new: bool) -> None:
    """Zaloguj zápis scrapu do Udalostí — rovnaký formát ako admin/klient
    úprava objednávky (`OrderViewSet._log_order_audit`), len s
    `actor_label="EduPage"` namiesto mena osoby (user 3.9.2026: nech je v
    Udalostiach vidno školu po škole, čo scrape reálne zmenil, nie len
    súhrnný `cron_run`). Bez reálnej zmeny dát sa nezaloguje nič — inak by
    hodinový 24/7 preview beh zaplavil Udalosti no-op zápismi z každej
    školy, každú hodinu.
    """
    from api.models import EventLog
    from api.services.event_log_service import build_nested_dict_diff, log_event

    new_data = order.data or {}
    if previous_data == new_data:
        return
    changed_meals = [
        meal_type
        for meal_type in (*_ALL_MEALS, *_EXTRA_MEAL_KEYS)
        if previous_data.get(meal_type, {}) != new_data.get(meal_type, {})
    ]
    event_type = (
        EventLog.EventType.ORDER_ADMIN_CREATE
        if is_new
        else EventLog.EventType.ORDER_ADMIN_UPDATE
    )
    verb = "zadal(a)" if is_new else "upravil(a)"
    log_event(
        event_type,
        actor=None,
        actor_label="EduPage",
        prevadzka=order.prevadzka,
        summary=f"EduPage {verb} objednávku (prevádzka: {order.prevadzka}) na {order.date}.",
        payload={
            "order_id": order.pk,
            "date": str(order.date),
            "prevadzka_id": order.prevadzka_id,
            "prevadzka_nazov": str(order.prevadzka) if order.prevadzka else None,
            "changed_meals": changed_meals,
            "changes": build_nested_dict_diff(previous_data, new_data),
            "meals": {
                meal_type: new_data.get(meal_type, {}) for meal_type in changed_meals
            },
        },
    )


def _apply_scrape(existing_data, imported_data, requested_meals):
    """Vlož výsledok scrapu s UPDATE sémantikou (nie ADD).

    Scrape je autoritatívny pre vyžiadané jedlá: každé z nich sa prepíše tým, čo
    EduPage vrátil, a ak dnes kleslo na nulu, VYMAŽE sa. Bez toho by po zrušení
    objednávky ostala v prehľade stará hodnota. Nevyžiadané jedlá ostávajú netknuté.
    """
    result = dict(existing_data or {})
    meals = _ALL_MEALS if requested_meals is None else requested_meals
    for meal_type in (*meals, *_EXTRA_MEAL_KEYS):
        scraped = imported_data.get(meal_type)
        if scraped:
            result[meal_type] = scraped
        else:
            result.pop(meal_type, None)
    return result


def _apply_partial_menu_scrape(
    existing_data: dict,
    imported_data: dict,
    meal_type: str = PARTIAL_LUNCH_MEAL,
    letters: tuple[str, ...] = PARTIAL_LUNCH_MENU_LETTERS,
) -> dict:
    """Zapíš len zadané menu písmená (B/C) pre `meal_type`, nič iné.

    Na rozdiel od `_apply_scrape` (celý meal bucket sa prepíše/zmaže) toto len
    prepíše menu písmená `letters` v `menuCounts` pre každú porciu — Menu A,
    diéty aj iné jedlá ostávajú netknuté. Používa sa na predbežný scrape 1-2
    dni pred aktuálnym dňom (kuchyňa dostane skorý odhad Menu B/C, ktoré má
    skoršiu EduPage uzávierku — user 2.9.2026). Deň samotný potom prepíše
    normálny plný `_apply_scrape`, ktorý je autoritatívny.

    Porcia, ktorá v čerstvom scrape B/C vôbec nemá (0 objednávok), sa v
    `menuCounts` na dané písmeno vynuluje/vymaže — inak by po odhlásení ostal
    v predbežnom odhade zastaraný počet z predošlého behu.
    """
    result = dict(existing_data or {})
    existing_meal = dict(result.get(meal_type) or {})
    imported_meal = (imported_data or {}).get(meal_type) or {}

    new_meal: dict = {}
    for portion_name in set(existing_meal) | set(imported_meal):
        existing_counts = existing_meal.get(portion_name) or {}
        imported_counts = imported_meal.get(portion_name) or {}
        menu_counts = dict(existing_counts.get("menuCounts") or {})
        imported_menu_counts = imported_counts.get("menuCounts") or {}
        for letter in letters:
            if letter in imported_menu_counts:
                menu_counts[letter] = imported_menu_counts[letter]
            else:
                menu_counts.pop(letter, None)
        diets = existing_counts.get("diets") or {}
        if menu_counts or diets:
            new_meal[portion_name] = {"menuCounts": menu_counts, "diets": diets}

    if new_meal:
        result[meal_type] = new_meal
    else:
        result.pop(meal_type, None)
    return result


def _dispatch_chained_reports(
    chained_reports: list[list[str]] | None,
    date_strs: list[str],
    scrape_failed: bool,
) -> list[dict]:
    """Queue the daily reports that were waiting on this scrape (issue #474).

    One report per (meal set × imported date), addressed to the exact date the
    scrape just wrote — not to a date guessed from the clock. Returns what was
    dispatched so the scrape summary can carry it.
    """
    if not chained_reports or not date_strs:
        return []

    dispatched = []
    for meals in chained_reports:
        for date_str in date_strs:
            send_daily_report_task.apply_async(
                kwargs={
                    "meals": list(meals),
                    "date_str": date_str,
                    "scrape_failed": scrape_failed,
                }
            )
            dispatched.append({"meals": list(meals), "date": date_str})

    logger.info(
        "Chained %d daily report(s) after the scrape (scrape_failed=%s): %s",
        len(dispatched),
        scrape_failed,
        dispatched,
    )
    return dispatched


def _scrape_target_dates(
    date_str: str | None,
    meal_types: list[str] | None,
    target_next_workday: bool = False,
):
    """Best-effort resolution of the dates a scrape run targets.

    Used on the give-up path, where the run blew up before (or while) computing
    them. Returns an empty list when even this cannot be determined.
    """
    import datetime

    from django.utils import timezone

    from api.services import _next_workday

    if date_str:
        return [date_str]

    today = timezone.localdate()
    if not meal_types:
        target: datetime.date = _next_workday(today) if target_next_workday else today
        return [target.isoformat()]

    from api.models import GlobalSettings

    try:
        gs = GlobalSettings.objects.get(pk=1)
    except Exception:
        logger.exception("Cannot resolve scrape target dates without GlobalSettings")
        return []

    dates = set()
    for meal_type in meal_types:
        _, is_day_before = gs.edupage_scrape_schedule_for(meal_type)
        target = _next_workday(today) if is_day_before else today
        dates.add(target.isoformat())
    return sorted(dates)


def _handle_scrape_give_up(
    exc: Exception,
    date_str: str | None,
    meal_types: list[str] | None,
    chained_reports: list[list[str]] | None,
    target_next_workday: bool = False,
) -> None:
    """Record an exhausted scrape and still send its chained reports, flagged."""
    from api.models import EventLog
    from api.services.event_log_service import log_event

    date_strs = _scrape_target_dates(date_str, meal_types, target_next_workday)

    try:
        # CRON_FAILED, nie CRON_SKIPPED: preskočenie znamená „víkend alebo voľný
        # deň, nemalo sa čo diať". Vyčerpaný scrape je zlyhanie a v tabuľke
        # udalostí musí vyzerať inak, inak sa stratí medzi bežnými víkendmi.
        log_event(
            EventLog.EventType.CRON_FAILED,
            actor_label="cron",
            summary=(
                "EduPage scrape zlyhal aj po opakovaniach — denný report ide "
                "von s upozornením, že počty nemusia byť finálne."
            ),
            payload={
                "task": "scrape_edupage_orders_task",
                "error": str(exc),
                "meal_types": meal_types,
                "dates": date_strs,
                "chained_reports": chained_reports or [],
            },
        )
    except Exception:
        logger.exception("Failed to log the exhausted EduPage scrape")

    _dispatch_chained_reports(chained_reports, date_strs, scrape_failed=True)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def scrape_edupage_orders_task(
    self,
    date_str: str | None = None,
    meal_types: list[str] | None = None,
    chained_reports: list[list[str]] | None = None,
    connection_id: int | None = None,
    exclude_connection_ids: list[int] | None = None,
    target_next_workday: bool = False,
    days_ahead: int | None = None,
):
    """
    Scrape mealsGuest HTML for all Edupage operations and upsert DailyOrder records.

    Called by Celery Beat before each meal deadline so order counts are ready when
    the kitchen needs them. Can also be triggered manually via the admin API.

    ``chained_reports`` holds the meal sets whose daily report must go out once
    this import has landed (issue #474). Chaining replaces the old arrangement of
    two independent crontabs separated by a 10-minute gap, which was an
    assumption rather than a guarantee: a slow or retrying scrape let the report
    leave with counts the import had not written yet. Each report is dispatched
    for the exact date(s) this run imported, so the report can no longer describe
    a different day than the one that was just scraped.

    ``connection_id`` / ``exclude_connection_ids`` scope the run to (or away
    from) one `EdupageConnection` — used by the British School dedicated
    schedule (#535), which scrapes on its own crontab (12:15 the day before)
    separate from the shared GlobalSettings meal deadlines, so it must be
    excluded from the deadline-derived runs to avoid a redundant second scrape.
    ``target_next_workday`` mirrors a `deadline_*_is_day_before` meal (target =
    the next workday, not today) for a run that has no `meal_types` of its own
    to read that flag from.

    ``days_ahead`` runs an hourly "preview" scrape instead of the deadline-driven
    one (2.9.2026): scrapes today through today + `days_ahead`, full `_apply_scrape`
    — same UPDATE-not-ADD semantics as the deadline run, so re-scraping the same
    day every hour is safe/idempotent. Per (date, meal_type) it only scrapes while
    that meal's own authoritative deadline scrape hasn't fired yet for that date
    (`_meal_scrape_deadline_passed`, read from `GlobalSettings` the same way the
    deadline-driven run resolves its targets) — once it has, the preview stays
    off that (date, meal_type) for the rest of the day, so it can no longer
    clobber a manual admin correction made after the authoritative scrape
    (2026-09-03: it did exactly that to two orders). A date with every meal past
    its deadline drops out of the window entirely. Day-off dates in the window
    are dropped rather than shifted — this is a rolling preview, not "the next N
    business days". Mutually exclusive with `meal_types`-driven deadline
    resolution; ignored when `date_str` is given (an explicit single-date run,
    e.g. manual trigger).
    """
    try:
        import datetime
        from copy import deepcopy

        from django.db import transaction
        from django.utils import timezone

        from api.cache_service import clear_gramage_dashboard_cache
        from api.edupage_scraper import (
            EdupageScraper,
            allowed_diet_names,
            build_prevadzka_matches,
            nest_order_data_by_category,
            prevadzky_without_match,
        )
        from api.models import DailyOrder, GlobalSettings
        from api.scheduling import business_days, closed_dates_for_prevadzky, is_day_off
        from api.services import _next_workday
        from api.services.edupage_connection_service import edupage_operations
        from api.signals import _meal_types_label_sk
        from api.utils import filter_order_data_for_prevadzka

        # Dátumy pridané nižšie ako predbežný Menu B/C scrape (1-2 dni vopred) —
        # tie sa pri zápise zlúčia cez `_apply_partial_menu_scrape`, nie plným
        # `_apply_scrape`. Prázdne pri manuálnom behu s explicitným `date_str`.
        partial_dates: set = set()

        valid_meal_types = {"breakfast", "lunch", "olovrant"}
        if isinstance(meal_types, str):
            meal_types = [meal_types]
        if meal_types is not None:
            invalid = [meal for meal in meal_types if meal not in valid_meal_types]
            if invalid:
                logger.error(
                    "scrape_edupage_orders_task: invalid meal_types=%s, no retry",
                    invalid,
                )
                return {"error": "invalid_meal_type", "meal_types": meal_types}

        date_to_meals: dict[datetime.date, list[str] | None]
        if date_str:
            target_date = datetime.date.fromisoformat(date_str)
            date_to_meals = {target_date: meal_types}
        else:
            try:
                gs = GlobalSettings.objects.get(pk=1)
            except GlobalSettings.DoesNotExist:
                logger.error(
                    "scrape_edupage_orders_task: GlobalSettings(pk=1) missing, no retry"
                )
                return {
                    "error": "missing_global_settings",
                    "meal_types": meal_types,
                }
            if not getattr(gs, "edupage_auto_scrape_enabled", True):
                logger.info(
                    "scrape_edupage_orders_task: automatic EduPage scrape is disabled"
                )
                return {
                    "scraped": 0,
                    "errors": 0,
                    "skipped": 0,
                    "dates": [],
                    "meal_types": meal_types,
                    "disabled": True,
                }

            today = timezone.localdate()
            if days_ahead is not None:
                # Hodinový "preview" beh: nasledujúcich `days_ahead + 1`
                # PRACOVNÝCH dní od dnes (#588), ale len tie jedlá, ktorých
                # autoritatívny (deadline) scrape pre daný dátum ešte
                # neprebehol (#_meal_scrape_deadline_passed) — po ňom je
                # preview beh zbytočný a navyše by prepísal prípadnú ručnú
                # admin opravu spravenú medzitým. Voľné dni sa vynechajú a
                # okno sa o ne predĺži (nie len zmenší) — inak by piatkový beh
                # (kalendárne piatok+sobota+nedeľa) nevidel žiadny nadchádzajúci
                # pracovný deň okrem piatku, hoci pondelok/utorok už majú
                # jedálny lístok pripravený. Deň, ktorému už všetky jedlá
                # "vydeadlinovali" (typicky dnešok večer po olovrantovom
                # scrape), sa z okna celkom vynechá. Prázdne okno nie je chyba.
                now_local = timezone.localtime()
                date_to_meals = {}
                for candidate in business_days(today, count=days_ahead + 1):
                    pending_meals = [
                        meal_type
                        for meal_type in _ALL_MEALS
                        if not _meal_scrape_deadline_passed(
                            gs, meal_type, candidate, now_local
                        )
                    ]
                    if pending_meals:
                        date_to_meals[candidate] = pending_meals
            elif meal_types is None:
                target_date = _next_workday(today) if target_next_workday else today
                date_to_meals = {target_date: None}
            else:
                date_to_meals = {}
                for meal_type in meal_types:
                    _, is_day_before = gs.edupage_scrape_schedule_for(meal_type)
                    target_date = _next_workday(today) if is_day_before else today
                    target_meals = date_to_meals.setdefault(target_date, [])
                    assert target_meals is not None
                    target_meals.append(meal_type)

            # Skip only the dates this run actually resolved to that are
            # themselves a day off — not "today" (the day the cron fires).
            # A Sun-Thu schedule with `target_next_workday`/`*_is_day_before`
            # fires on Sunday precisely to prepare Monday, and Sunday itself
            # is always a weekend, so checking "today" would always bail.
            skip_reason = None
            for skip_date in list(date_to_meals):
                skip_reason = _cron_skip_check("scrape_edupage_orders_task", skip_date)
                if skip_reason is not None:
                    del date_to_meals[skip_date]

            if not date_to_meals:
                return {
                    "scraped": 0,
                    "errors": 0,
                    "skipped": 0,
                    "dates": [],
                    "meal_types": meal_types,
                    "skipped_run": True,
                    "reason": skip_reason,
                }

            # Predbežný Menu B/C scrape 1-2 dni vopred, napojený na obedový beh
            # (user 2.9.2026): niektoré školy majú pre Menu B/C skoršiu EduPage
            # uzávierku, kuchyňa chce vidieť odhad skôr. Deň, ktorý je už bežným
            # cieľom tohto behu, sa nepridáva znova — plný scrape má prednosť.
            if meal_types is not None and PARTIAL_LUNCH_MEAL in meal_types:
                for partial_days_ahead in PARTIAL_LUNCH_DAYS_AHEAD:
                    candidate = today + datetime.timedelta(days=partial_days_ahead)
                    if candidate in date_to_meals or is_day_off(candidate):
                        continue
                    date_to_meals[candidate] = [PARTIAL_LUNCH_MEAL]
                    partial_dates.add(candidate)

        scraper = EdupageScraper()
        # Whitelist diét sa číta raz za beh — je rovnaký pre všetky prevádzky.
        allowed_diets = allowed_diet_names()
        scraped = errors = skipped = 0

        operations = edupage_operations(connection_id=connection_id)
        if exclude_connection_ids:
            operations = [
                operation
                for operation in operations
                if operation["connection_id"] not in exclude_connection_ids
            ]

        for operation in operations:
            prevadzky = list(operation["prevadzky"])
            if not prevadzky:
                logger.warning(
                    "scrape_edupage_orders_task: %s nemá žiadnu prevádzku — preskakujem",
                    operation["name"],
                )
                skipped += 1
                continue

            # Viac prevádzok → EduPage riadky rozdelíme podľa `edupage_match`.
            # Jedna prevádzka → split nerobíme a všetko ide do nej.
            by_nazov = {p.nazov: p for p in prevadzky}
            # Voľno prevádzky (#490): na taký deň sa jej plán nezakladá vôbec.
            # Jeden dotaz na celok, nie na každý (prevádzka × deň).
            scrape_dates = list(date_to_meals)
            closed_by_prevadzka = closed_dates_for_prevadzky(
                [p.id for p in prevadzky], min(scrape_dates), max(scrape_dates)
            )
            matches = build_prevadzka_matches(prevadzky)
            bez_matchu = prevadzky_without_match(prevadzky)
            if len(prevadzky) > 1 and bez_matchu:
                logger.error(
                    "scrape_edupage_orders_task: %s má %d prevádzok, ale %s nemá "
                    "edupage_match — preskakujem, aby sa objem nezapísal nesprávne",
                    operation["name"],
                    len(prevadzky),
                    ", ".join(bez_matchu),
                )
                skipped += 1
                continue

            for target_date, requested_meals in date_to_meals.items():
                try:
                    result = scraper.scrape(
                        operation["url"],
                        target_date,
                        prevadzka_matches=matches if len(prevadzky) > 1 else None,
                        allowed_diets=allowed_diets,
                    )
                except Exception:
                    logger.exception(
                        "scrape_edupage_orders_task: failed for %s",
                        operation["url"],
                    )
                    errors += 1
                    continue

                if result.config_notes:
                    logger.warning(
                        "scrape_edupage_orders_task: config drift for %s on %s: %s",
                        operation["name"],
                        target_date,
                        result.config_notes,
                    )
                if result.attention:
                    logger.info(
                        "scrape_edupage_orders_task: manual check for %s on %s: %s",
                        operation["name"],
                        target_date,
                        result.attention,
                    )
                if result.unmapped_letters:
                    logger.warning(
                        "scrape_edupage_orders_task: neznáme diéty pre %s na %s: %s "
                        "— porcie sú započítané, ale diétu treba založiť v appke",
                        operation["name"],
                        target_date,
                        result.unmapped_letters,
                    )
                if result.skipped_letters:
                    logger.info(
                        "scrape_edupage_orders_task: písmená vynechané podľa configu "
                        "(skip=True) pre %s na %s: %s",
                        operation["name"],
                        target_date,
                        result.skipped_letters,
                    )

                # Jedna prevádzka → celý objem jej; viac → podľa edupage_match.
                if len(prevadzky) > 1:
                    data_by_nazov = result.order_data_by_prevadzka
                else:
                    data_by_nazov = {prevadzky[0].nazov: result.order_data}

                for nazov, prevadzka in by_nazov.items():
                    if target_date in closed_by_prevadzka.get(prevadzka.id, set()):
                        logger.info(
                            "scrape_edupage_orders_task: %s má na %s voľno — "
                            "plán nezakladám",
                            nazov,
                            target_date,
                        )
                        skipped += 1
                        continue

                    # Pri rozdelenom celku priraď každej prevádzke len tie flagy,
                    # ktorých porcie do nej reálne padli; config_notes sú celok-wide.
                    if len(prevadzky) > 1:
                        attention_for_prevadzka = result.attention_by_prevadzka.get(
                            nazov, []
                        )
                        unmapped_for_prevadzka = result.unmapped_by_prevadzka.get(
                            nazov, []
                        )
                        uncertain_for_prevadzka = result.uncertain_by_prevadzka.get(
                            nazov, []
                        )
                    else:
                        attention_for_prevadzka = result.attention
                        unmapped_for_prevadzka = result.unmapped_letters
                        uncertain_for_prevadzka = result.uncertain_letters

                    nested_order_data = nest_order_data_by_category(
                        data_by_nazov.get(nazov, {}), nazov
                    )
                    nested_order_data = filter_order_data_for_prevadzka(
                        nested_order_data, nazov
                    )
                    imported_data = _filter_order_data_by_meals(
                        nested_order_data, requested_meals
                    )

                    # Skutočné zlyhanie scrapu (chýbajúci/pokazený prehlad blok,
                    # nezmapované písmeno, riadok bez prevádzky) - neprepisujeme
                    # existujúce dáta prázdnom, mohli by sme zmazať platné počty.
                    # `uncertain_letters` sem zámerne nepatrí — je to len "over ma"
                    # signál (ako `config_notes`), nie signál zlyhania scrapu.
                    if not imported_data and (
                        result.warnings or result.unmapped_letters
                    ):
                        logger.info(
                            "scrape_edupage_orders_task: empty result for %s/%s on %s "
                            "meals=%s (warnings=%s, unmapped=%s)",
                            operation["name"],
                            nazov,
                            target_date,
                            requested_meals,
                            result.warnings,
                            result.unmapped_letters,
                        )
                        skipped += 1
                        continue

                    # Úspešný scrape (aj s nulovými počtami) je autoritatívny:
                    # prepíše vyžiadané jedlá a vyčistí tie, čo dnes klesli na nulu.
                    # Explicitný záznam (aj prázdny) odlíši "0 objednávok" od
                    # "nikdy nescrapované". Predbežný dátum (1-2 dni vopred) je
                    # výnimka: zapíše len Menu B/C, ostatné jedlá/porcie na tento
                    # deň ostávajú netknuté (deň samotný to neskôr prepíše plne).
                    with transaction.atomic():
                        (
                            order,
                            created,
                        ) = DailyOrder.objects.select_for_update().get_or_create(
                            prevadzka=prevadzka,
                            date=target_date,
                            defaults={"user": operation["user"], "data": {}},
                        )
                        previous_data = deepcopy(order.data or {})
                        if target_date in partial_dates:
                            order.data = _apply_partial_menu_scrape(
                                order.data, imported_data
                            )
                        else:
                            order.data = _apply_scrape(
                                order.data, imported_data, requested_meals
                            )
                        # Upozornenia posledného scrapu — prepíšeme (aj prázdnym),
                        # nech admin prehľad nezobrazuje výkričník z minulého behu,
                        # ktorý sa už medzitým vyriešil.
                        order.scrape_flags = {
                            "attention": list(attention_for_prevadzka),
                            "config_notes": list(result.config_notes),
                            "unmapped_diets": list(unmapped_for_prevadzka),
                            "uncertain_diets": list(uncertain_for_prevadzka),
                        }
                        order.save(update_fields=["data", "scrape_flags", "updated_at"])
                        _log_scrape_order_event(order, previous_data, created)
                    scraped += 1

        # Scrape prepísal DailyOrder.data pre tieto dni — gramage dashboard by
        # ich inak mohol ešte 5 minút ukazovať s počtami spred scrapu.
        for target_date in date_to_meals:
            clear_gramage_dashboard_cache(str(target_date))

        # Skutočne stiahnuté jedlá per deň — `meal_types` nižšie je len surový
        # task kwarg (často `null` pri `days_ahead` behu) a nehovorí, ktoré
        # jedlá po (2026-09-03/04) deadline-per-jedlo filtri v `date_to_meals`
        # reálne zostali. `None` = beh bez filtra (plný denný scrape),
        # zobrazené ako všetky tri jedlá.
        meals_by_date: dict[str, list[str]] = {
            str(target_date): (
                [meal for meal in _ALL_MEALS if meal in target_meals]
                if target_meals is not None
                else list(_ALL_MEALS)
            )
            for target_date, target_meals in date_to_meals.items()
        }
        summary = {
            "scraped": scraped,
            "errors": errors,
            "skipped": skipped,
            "dates": [str(target_date) for target_date in date_to_meals],
            "meal_types": meal_types,
            "meals_by_date": meals_by_date,
        }
        # Predbežné dátumy (partial_dates) dostali len Menu B/C odhad, nie plný
        # scrape — chained report na ne nesmie ísť, poslal by kuchyni neúplné
        # čísla ako keby boli finálne. Report čaká na deň, keď ho prepíše
        # autoritatívny plný `_apply_scrape`.
        dispatched = _dispatch_chained_reports(
            chained_reports,
            [
                str(target_date)
                for target_date in date_to_meals
                if target_date not in partial_dates
            ],
            scrape_failed=False,
        )
        if dispatched:
            summary["chained_reports_dispatched"] = dispatched
        logger.info("scrape_edupage_orders_task result: %s", summary)
        # "2026-09-04: obed/olovrant" per deň — nech je z logu priamo vidno,
        # ktoré jedlá sa reálne stiahli (napr. že raňajky po 1:35 deadline-e
        # už chýbajú), nie len súhrnný počet prevádzok.
        scraped_dates = ", ".join(
            f"{date_str}: {_meal_types_label_sk(meals)}"
            for date_str, meals in meals_by_date.items()
        )
        run_label = (
            f"Predbežný náhľad (+{days_ahead} dni)"
            if days_ahead is not None
            else "Cron"
        )
        _log_cron_run(
            "scrape_edupage_orders_task",
            f"{run_label} stiahol EduPage objednávky ({scraped_dates}): "
            f"{scraped} prevádzok, {errors} chýb, {skipped} preskočených.",
            summary,
        )
        return summary

    except Exception as exc:
        logger.exception("scrape_edupage_orders_task failed, retrying...")
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            # Retries are spent. The kitchen still needs numbers, so the chained
            # report goes out — but explicitly marked as possibly not final,
            # instead of quietly looking like a normal day (issue #474).
            _handle_scrape_give_up(
                exc, date_str, meal_types, chained_reports, target_next_workday
            )
            raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_daily_report_task(
    self,
    meals: list[str] | None = None,
    date_str: str | None = None,
    scrape_failed: bool = False,
):
    """
    Celery task: send daily order report.

    Normally chained after `scrape_edupage_orders_task` (issue #474), which
    passes the exact date it imported. The standalone Celery Beat schedule is
    only used when the EduPage auto-scrape is off; there the date defaults to
    yesterday.

    Args:
        meals: List of meals to include (breakfast, lunch, olovrant).
               If None, includes all meals.
        date_str: Target date in YYYY-MM-DD format. Defaults to yesterday.
        scrape_failed: Set by the chaining scrape when its retries were
               exhausted — the report still goes out, but says so.
    """
    try:
        import datetime

        from django.core import management
        from django.utils import timezone

        from api.models import GlobalSettings

        # Determine target date
        if date_str:
            target_date = datetime.date.fromisoformat(date_str)
        else:
            gs = GlobalSettings.objects.filter(pk=1).first()
            if gs is not None and not getattr(gs, "daily_report_enabled", True):
                logger.info("send_daily_report_task: daily reports are disabled")
                # Vypnutý report je tichý stav, ktorý sa zvonku nedá odlíšiť od
                # rozbitého cronu — preto sa zapisuje.
                _log_cron_run(
                    "send_daily_report_task",
                    "Cron: denný report neodoslaný — je vypnutý v nastaveniach.",
                    {"sent": False, "reason": "daily_report_disabled", "meals": meals},
                )
                return {"skipped": True, "reason": "daily_report_disabled"}

            target_date = timezone.localdate() - datetime.timedelta(days=1)
            # Check the day the report is actually ABOUT (yesterday), not
            # today — the two only ever differ by weekday name, but "today"
            # is the wrong date on principle (see `_cron_skip_check`).
            if (
                reason := _cron_skip_check("send_daily_report_task", target_date)
            ) is not None:
                return {"skipped": True, "reason": reason}

        # Build meal argument
        meals_arg = ",".join(meals) if meals else "breakfast,lunch,olovrant"

        command_args = [
            f"--date={target_date.isoformat()}",
            f"--meals={meals_arg}",
        ]
        if scrape_failed:
            command_args.append("--data-may-be-stale")

        # Call the management command
        management.call_command("send_order_report", *command_args)

        logger.info(
            "Daily report sent for %s (meals: %s, scrape_failed=%s)",
            target_date.isoformat(),
            meals_arg,
            scrape_failed,
        )
        _log_cron_run(
            "send_daily_report_task",
            f"Cron odoslal denný report na {target_date} ({meals_arg})."
            + (" Počty nemusia byť finálne." if scrape_failed else ""),
            {
                "sent": True,
                "date": target_date.isoformat(),
                "meals": meals_arg.split(","),
                "scrape_failed": scrape_failed,
            },
        )
        return f"Report sent for {target_date} with meals: {meals_arg}"
    except Exception as exc:
        logger.exception("send_daily_report_task failed, retrying...")
        _log_cron_failure(
            "send_daily_report_task", exc, {"meals": meals, "date": date_str}
        )
        raise self.retry(exc=exc)


#: Ako dlho sa držia záznamy o udalostiach. Audit slúži na dohľadanie „kto čo
#: zmenil" v čerstvej prevádzke, nie na dlhodobú archiváciu — bez stropu
#: tabuľka rastie donekonečna.
EVENT_LOG_RETENTION_DAYS = 7

#: Objednávkové eventy (`order_admin_*`) žijú dlhšie než ostatný audit — slúžia
#: na spätné dohľadávanie sporov s prevádzkou ("kto/kedy/koľko objednal"),
#: 7 dní by na to bolo príliš krátko.
ORDER_EVENT_LOG_RETENTION_DAYS = 90


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def purge_old_event_logs_task(self, days: int | None = None):
    """Zmaže záznamy udalostí staršie než `days` (default 7; objednávky 90).

    Beží denne. Maže po dávkach, aby jedna transakcia nedržala zámok nad celou
    tabuľkou, keď sa raz nakopí väčší objem. Explicitný `days` (napr. testy)
    prepíše retenciu jednotne pre všetky typy eventov vrátane objednávok.
    """
    import datetime

    from django.db.models import Q

    from api.models import EventLog

    order_event_types = [
        EventLog.EventType.ORDER_ADMIN_CREATE,
        EventLog.EventType.ORDER_ADMIN_UPDATE,
        EventLog.EventType.ORDER_ADMIN_DELETE,
    ]
    retention = EVENT_LOG_RETENTION_DAYS if days is None else int(days)
    order_retention = ORDER_EVENT_LOG_RETENTION_DAYS if days is None else int(days)
    cutoff = timezone.now() - datetime.timedelta(days=retention)
    order_cutoff = timezone.now() - datetime.timedelta(days=order_retention)

    try:
        deleted_total = 0
        while True:
            batch_ids = list(
                EventLog.objects.filter(
                    Q(created_at__lt=cutoff) & ~Q(event_type__in=order_event_types)
                    | Q(created_at__lt=order_cutoff, event_type__in=order_event_types)
                ).values_list("pk", flat=True)[:1000]
            )
            if not batch_ids:
                break
            deleted, _ = EventLog.objects.filter(pk__in=batch_ids).delete()
            deleted_total += deleted

        logger.info(
            "purge_old_event_logs_task: zmazaných %s udalostí (retencia %s dní, "
            "objednávky %s dní)",
            deleted_total,
            retention,
            order_retention,
        )
        return {
            "deleted": deleted_total,
            "retention_days": retention,
            "order_retention_days": order_retention,
        }
    except DatabaseError as exc:
        logger.warning("purge_old_event_logs_task: DB chyba, skúšam znova: %s", exc)
        raise self.retry(exc=exc)


@shared_task
def cache_closed_day_pdf_task(date_str: str) -> None:
    """Predgeneruje a nacachuje PDF gramáže po uzavretí dňa (#528).

    Volané asynchrónne z `ClosedDayViewSet.create()` — WeasyPrint (stovky ms
    až sekundy pri viacerých prevádzkach/diétach) predtým bežal priamo v
    HTTP requeste admina, ktorý klikol "uzavrieť deň", a blokoval web worker
    (code review 2026-08-31). Zlyhanie tu nesmie nič zhodiť: PDF sa pri
    cache-miss aj tak domodeluje na požiadanie (`gramage-dashboard-pdf`),
    takže si len zaloguje a skončí.
    """
    import datetime

    from api.cache_service import (
        CLOSED_DAY_PDF_TIMEOUT,
        get_closed_day_pdf_cache_key,
        set_cached,
    )
    from api.services.gramage_pdf_service import render_gramage_dashboard_pdf

    try:
        target_date = datetime.date.fromisoformat(date_str)
        pdf_bytes = render_gramage_dashboard_pdf(date_str)
        set_cached(
            get_closed_day_pdf_cache_key(target_date.isoformat()),
            pdf_bytes,
            timeout=CLOSED_DAY_PDF_TIMEOUT,
        )
    except Exception:
        logger.exception(
            "cache_closed_day_pdf_task: nepodarilo sa predgenerovať PDF gramáže "
            "pre uzavretý deň %s",
            date_str,
        )


@shared_task
def refresh_gramage_dashboard_cache_task(date_str: str) -> None:
    """Prepočíta a znova nacachuje gramage dashboard pre daný deň.

    Volané asynchrónne (`.delay()`) z `schedule_gramage_dashboard_refresh`
    (`api/cache_service.py`) po každej zmene `DailyOrder`/`Prevadzka` — bez
    toho admin po úprave objednávky/poznámky videl starý stav až
    `GRAMAGE_DASHBOARD_TIMEOUT` (5 min). Zlyhanie tu nesmie nič zhodiť: pri
    cache-miss sa dashboard aj tak domodeluje synchrónne na požiadanie
    (`get_cached_gramage_dashboard_data`), takže si len zaloguje a skončí.
    """
    from api.cache_service import (
        GRAMAGE_DASHBOARD_TIMEOUT,
        get_gramage_dashboard_cache_key,
        set_cached,
    )
    from api.services.meal_plan_service import MealPlanService

    try:
        data = MealPlanService.gramage_dashboard(date_str)
        set_cached(
            get_gramage_dashboard_cache_key(date_str),
            data,
            timeout=GRAMAGE_DASHBOARD_TIMEOUT,
        )
    except Exception:
        logger.exception(
            "refresh_gramage_dashboard_cache_task: nepodarilo sa prepočítať "
            "gramage dashboard pre %s",
            date_str,
        )
