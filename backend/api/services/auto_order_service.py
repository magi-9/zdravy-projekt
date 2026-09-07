"""Auto-order service: pure business logic with no side-effects beyond DB writes."""

import datetime
import logging
from typing import Any, Dict, List, Optional

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..exceptions import ClosedDayOrderModificationError
from ..models import Celok, DailyOrder, Prevadzka
from ..order_data import MEAL_KEYS, OrderData, safe_count
from ..scheduling import closed_dates_for_prevadzky, is_weekend, next_business_day

logger = logging.getLogger(__name__)


def _is_order_empty(data: Dict[str, Any]) -> bool:
    """Return True if order data contains zero menu portions across all meals."""
    return OrderData(data).is_empty()


def _next_workday(from_date: datetime.date) -> datetime.date:
    """Najbližší deň na objednanie striktne po `from_date`.

    Cez `api.scheduling`, takže okrem víkendu preskočí aj celosystémový
    `Holiday` — auto-objednávka nemá mieriť na deň, kedy kuchyňa nevarí (#489).
    Voľno konkrétnej prevádzky sa tu riešiť nedá (dátum je jeden pre celý beh),
    rieši sa nižšie preskočením tej prevádzky.
    """
    return next_business_day(from_date + datetime.timedelta(days=1))


def _last_non_empty_order(user: User, before_date: datetime.date) -> DailyOrder | None:
    """
    Return the most recent non-empty order before the given date.

    Drafts are never persisted via the normal API path, so every stored order
    is treated as submitted.
    """
    orders = (
        DailyOrder.objects.filter(
            user=user,
            date__lt=before_date,
        )
        .select_related("prevadzka")
        .prefetch_related("prevadzka__visible_portion_types")
        .order_by("-date")
    )

    for order in orders:
        if not _is_order_empty(order.data or {}):
            return order
    return None


def _normalise_meal(meal: Any) -> Dict[str, Any]:
    """
    Return a guaranteed category-nested meal dict.

    Legacy records may have flat shape: {meal: {"menuCounts": {...}}}.
    Auto-orders must write category-nested shape so the serializer accepts
    any subsequent client resubmit.  Flat meals are promoted to a single
    synthetic category named after the meal key they came from.
    """
    return OrderData.normalise_meal(meal)


def _allowed_menus_for_date(
    visible_menus: List[str],
    day_restrictions: Optional[Dict[str, List[int]]],
    date: datetime.date,
) -> List[str]:
    """Ktoré z `visible_menus` sa dá na `date` objednať — rovnaká sémantika
    ako `filterMenusByDay` (frontend `useOrder.ts`) a
    `_enforce_menu_day_restrictions` (serializers.py)."""
    if not day_restrictions:
        return list(visible_menus)
    weekday = date.isoweekday()
    return [
        menu
        for menu in visible_menus
        if not day_restrictions.get(menu) or weekday in day_restrictions[menu]
    ]


def _meal_allowed_on_date(
    meal_key: str,
    day_restrictions: Optional[Dict[str, List[int]]],
    date: datetime.date,
) -> bool:
    """Rovnaká sémantika ako `_enforce_meal_day_restrictions` (serializers.py)."""
    if not day_restrictions:
        return True
    allowed_days = day_restrictions.get(meal_key)
    if not allowed_days:
        return True
    return date.isoweekday() in allowed_days


def _is_leaf_payload(value: Any) -> bool:
    return isinstance(value, dict) and ("menuCounts" in value or "diets" in value)


def _redirect_counts_map(counts: Any, allowed_set: set, fallback: Optional[str]) -> Any:
    if not isinstance(counts, dict):
        return counts
    result: Dict[str, int] = {}
    for menu, count in counts.items():
        target = menu if menu in allowed_set else fallback
        if target is None:
            continue
        result[target] = result.get(target, 0) + safe_count(count)
    return result


def _redirect_restricted_menus_in_leaf(
    leaf: Dict[str, Any], allowed_set: set, fallback: Optional[str]
) -> None:
    if "menuCounts" in leaf:
        leaf["menuCounts"] = _redirect_counts_map(
            leaf["menuCounts"], allowed_set, fallback
        )
    for pack_field in ("packSeparately", "packSeparatelyGn"):
        pack = leaf.get(pack_field)
        if isinstance(pack, dict) and isinstance(pack.get("menus"), dict):
            pack["menus"] = _redirect_counts_map(pack["menus"], allowed_set, fallback)


def _redirect_restricted_menus(
    meal_data: Dict[str, Any], allowed_menus: List[str]
) -> Dict[str, Any]:
    """Menu písmeno zakázané na cieľový deň (`menu_day_restrictions`, napr.
    menu B len v piatok) sa presunie do prvého dnes povoleného menu, namiesto
    toho, aby auto-objednávka skopírovala šablónu s menu, ktoré by na
    `_enforce_menu_day_restrictions` padlo a jej počty by jednoducho zmizli."""
    allowed_set = set(allowed_menus)
    fallback = allowed_menus[0] if allowed_menus else None
    for details in meal_data.values():
        if not isinstance(details, dict):
            continue
        if _is_leaf_payload(details):
            _redirect_restricted_menus_in_leaf(details, allowed_set, fallback)
            continue
        for portion_details in details.values():
            if isinstance(portion_details, dict) and _is_leaf_payload(portion_details):
                _redirect_restricted_menus_in_leaf(
                    portion_details, allowed_set, fallback
                )
    return meal_data


def _build_auto_data(
    template: DailyOrder,
    visible_meals: List[str],
    visible_portion_types: Optional[List[str]] = None,
    target_date: Optional[datetime.date] = None,
) -> Dict[str, Any]:
    """
    Copy only the allowed meals from the template, always in category-nested shape.
    If visible_meals is empty, all three meals are copied.

    `target_date`, keď je zadaný, navyše vynúti deň-špecifické obmedzenia
    (`meal_day_restrictions`, `menu_day_restrictions`): jedlo zakázané v ten
    deň sa vôbec neskopíruje (rovnako, akoby vo `visible_meals` nebolo), menu
    písmeno zakázané v ten deň sa presunie do prvého povoleného menu toho
    dňa (`_redirect_restricted_menus`) namiesto toho, aby zmizlo. Bez
    `target_date` (staršie volania) sa toto obmedzenie neaplikuje.
    """
    allowed = set(visible_meals) if visible_meals else set(MEAL_KEYS)
    # Raňajky sa štandardne kopírujú z predošlých raňajok, ale niektoré
    # prevádzky (napr. Bystrá škôlky) chcú raňajky napĺňať predošlým obedom —
    # viď `Prevadzka.auto_order_breakfast_source`.
    # `getattr(template, "prevadzka", None)` (nie priamy `template.prevadzka`),
    # lebo prevadzka je povinný FK — na neuloženom `DailyOrder(data=...)` bez
    # prevadzka_id (viď testy v TestBuildAutoData) by priamy prístup vyhodil
    # `RelatedObjectDoesNotExist`.
    prevadzka = getattr(template, "prevadzka", None)
    breakfast_source = (
        getattr(prevadzka, "auto_order_breakfast_source", "breakfast") or "breakfast"
    )
    meal_sources = {"breakfast": breakfast_source}

    meal_day_restrictions: Optional[Dict[str, List[int]]] = None
    allowed_menus_today: Optional[List[str]] = None
    if target_date is not None:
        meal_day_restrictions = getattr(prevadzka, "meal_day_restrictions", None) or {}
        menu_day_restrictions = getattr(prevadzka, "menu_day_restrictions", None) or {}
        prevadzka_visible_menus = list(getattr(prevadzka, "visible_menus", []) or [])
        if menu_day_restrictions and prevadzka_visible_menus:
            allowed_menus_today = _allowed_menus_for_date(
                prevadzka_visible_menus, menu_day_restrictions, target_date
            )

    data = {}
    for meal_key in MEAL_KEYS:
        meal_allowed = meal_key in allowed
        if meal_allowed and target_date is not None:
            meal_allowed = _meal_allowed_on_date(
                meal_key, meal_day_restrictions, target_date
            )
        if meal_allowed:
            source_key = meal_sources.get(meal_key, meal_key)
            raw = (template.data or {}).get(source_key, {})
            normalised = _normalise_meal(raw)
            if visible_portion_types:
                allowed_portion_types = set(visible_portion_types)
                normalised = {
                    name: values
                    for name, values in normalised.items()
                    if name in allowed_portion_types
                }
            if allowed_menus_today is not None:
                normalised = _redirect_restricted_menus(normalised, allowed_menus_today)
            data[meal_key] = normalised
        else:
            data[meal_key] = {}
    return data


def _edupage_prevadzka_ids() -> set[int]:
    """Return active prevádzka ids whose counts must come only from EduPage."""
    # Zámerne bez filtra na is_active: preskočiť navyše je neškodné, vytvoriť
    # auto-objednávku na EduPage prevádzke nie.
    prevadzka_ids = set(
        Prevadzka.objects.filter(
            celok__zdroj_objednavok=Celok.ZdrojObjednavok.EDUPAGE,
        ).values_list("id", flat=True)
    )

    return prevadzka_ids


def _scoped_is_empty(data: Dict[str, Any], meal_types: List[str]) -> bool:
    """`OrderData.is_empty()`, ale len pre vybranú podmnožinu jedál."""
    return OrderData(
        {meal: (data or {}).get(meal, {}) for meal in meal_types}
    ).is_empty()


def apply_auto_orders(
    target_date: datetime.date | None = None,
    meal_types: List[str] | None = None,
) -> Dict[str, Any]:
    """
    For every active non-staff client that has no order on target_date,
    find their last non-empty order and create an auto order.

    `meal_types` obmedzí beh len na tieto jedlá (#548) — raňajky a obed/olovrant
    majú inú uzávierku (typicky večer vopred vs. ráno v deň podávania), takže
    bežia v dvoch samostatných crontaboch namiesto jedného, ktorý by musel
    čakať na tú neskoršiu z oboch a auto-vyplnenie tej skoršej by prišlo
    zbytočne neskoro.

    `meal_types=None` (predvolené, používa ho aj ručné spustenie z admina) je
    pôvodné správanie: naplní VŠETKY viditeľné jedlá naraz a prevádzku, ktorá
    už má pre daný deň akýkoľvek riadok, preskočí bez zásahu doňho.

    S `meal_types` sa namiesto toho existujúci riadok (ak je) DOPĹŇA — naplnia
    sa len tie jedlá z `meal_types`, ktoré sú v ňom ešte prázdne; ostatné
    (manuálne zadané, alebo naplnené druhým behom) ostávajú nedotknuté. Vďaka
    tomu môže klient medzi oboma behmi pokojne upraviť čokoľvek zo svojej
    objednávky bez toho, aby to ten druhý beh prepísal.

    Returns a summary dict: {"created": [...], "skipped": int}
    """
    if target_date is None:
        # Use local date (Europe/Bratislava) — same timezone the rest of the app uses
        # for deadlines, monthly_summary, etc.  UTC diverges near local midnight and
        # across DST transitions, causing off-by-one target dates.
        today = timezone.localdate()
        target_date = _next_workday(today)

    # Safety: never auto-order on weekends
    if is_weekend(target_date):
        logger.info(
            "apply_auto_orders: target_date %s is a weekend, skipping.", target_date
        )
        return {"created": [], "skipped": 0, "date": str(target_date)}

    # A closed day is immutable.  This service runs outside an HTTP request, so
    # use the same central guard as interactive writes but skip instead of raising.
    from ..serializers import DailyOrderSerializer

    try:
        DailyOrderSerializer._enforce_day_open(target_date)
    except ClosedDayOrderModificationError:
        logger.info(
            "apply_auto_orders: target_date %s is closed, skipping.", target_date
        )
        return {"created": [], "skipped": 0, "date": str(target_date)}

    # Auto-objednávky sa vedú per prevádzka, nie per login: celok s tromi
    # prevádzkami musí dostať tri objednávky, nie jednu. Šablóna aj kontrola
    # "už existuje" preto filtrujú podľa prevádzky, NIE podľa `user` —
    # `DailyOrder.user` je iba audit toho, kto riadok naposledy zapísal
    # (viď `DailyOrderViewSet.get_queryset`: "Objednávka patrí prevádzke,
    # user je iba audit"). Skorší filter `user_id__in=client_ids` admin-
    # -nastavené objednávky (user=admin, keď prevádzka nemá klientský login)
    # z tejto úvahy úplne vyradil — nikdy sa nepoužili ako šablóna a systém
    # si "nevšimol", že prevádzka na daný deň objednávku už má.
    active_prevadzka_ids = set(
        Prevadzka.objects.filter(is_active=True).values_list("id", flat=True)
    )

    # V scoped behu (meal_types) treba dáta existujúceho riadku prečítať aj
    # dopísať doň, preto celý objekt, nie len id.
    existing_orders_by_prevadzka: Dict[int, DailyOrder] = {
        order.prevadzka_id: order
        for order in DailyOrder.objects.filter(
            date=target_date, prevadzka_id__in=active_prevadzka_ids
        )
    }

    # Preload: best (latest non-empty) template per prevádzka (1 query, no N+1)
    templates_by_prevadzka: Dict[int, DailyOrder] = {}
    decided_prevadzka_ids: set[int] = set()
    paused_prevadzka_ids: set[int] = set()
    for order in (
        DailyOrder.objects.filter(
            date__lt=target_date,
            prevadzka_id__in=active_prevadzka_ids,
        )
        .select_related("prevadzka", "user")
        .prefetch_related("prevadzka__visible_portion_types")
        .order_by("prevadzka_id", "-date")
    ):
        if order.prevadzka_id in decided_prevadzka_ids:
            continue
        if order.prevadzka.auto_order_paused:
            # Klient si objednávku vynuloval/zmazal — preklápanie je pre túto
            # prevádzku zastavené, kým znova nepošle reálnu objednávku (viď
            # `DailyOrderSerializer._sync_auto_order_pause`). Staršia neprázdna
            # objednávka spred vynulovania sa už ako šablóna nepoužije.
            decided_prevadzka_ids.add(order.prevadzka_id)
            paused_prevadzka_ids.add(order.prevadzka_id)
            continue
        if not _is_order_empty(order.data or {}):
            templates_by_prevadzka[order.prevadzka_id] = order
            decided_prevadzka_ids.add(order.prevadzka_id)

    edupage_prevadzka_ids = _edupage_prevadzka_ids()
    # Voľno prevádzky (#490): auto-objednávka ho musí rešpektovať rovnako ako
    # víkend — inak by prevádzka na prázdninách dostávala jedlo každý deň.
    closed_prevadzka_ids = {
        pid
        for pid, days in closed_dates_for_prevadzky(
            list(templates_by_prevadzka), target_date, target_date
        ).items()
        if days
    }
    created = []
    skipped = 0
    skipped_edupage = 0
    skipped_closed = 0

    for prevadzka_id, template in templates_by_prevadzka.items():
        if prevadzka_id in edupage_prevadzka_ids:
            skipped += 1
            skipped_edupage += 1
            continue

        if prevadzka_id in closed_prevadzka_ids:
            skipped += 1
            skipped_closed += 1
            continue

        existing_order = existing_orders_by_prevadzka.get(prevadzka_id)

        # Nescoped beh (ručné spustenie z admina): existujúci riadok — manuálny
        # aj z predošlého auto-behu — sa nedotýka, nech nezdvojí ani neprepíše
        # dáta pre jedlá, ktoré scoped beh mohol už naplniť.
        if meal_types is None and existing_order is not None:
            skipped += 1
            continue

        # `client` je tu len audit autora nového riadku (viď komentár vyššie
        # pri `active_prevadzka_ids`) — prevzatý od šablóny nech je ňou
        # ktokoľvek (klient aj admin). `user=None` (zmazaný login) jediný
        # prípad, kedy nemá zmysel pokračovať.
        client = template.user
        if client is None:
            skipped += 1
            continue

        visible_meals: List[str] = list(
            getattr(template.prevadzka, "visible_meals", []) or []
        )
        visible_portion_types = [
            portion_type.name
            for portion_type in template.prevadzka.visible_portion_types.all()
            if portion_type.is_active
        ]

        if meal_types is not None:
            # Scoped beh: naplň len tie jedlá z `meal_types`, ktoré sú
            # v existujúcom riadku (ak je) ešte prázdne — ostatné (manuálne,
            # alebo naplnené druhým behom) nechaj tak.
            scope = [
                meal
                for meal in meal_types
                if not visible_meals or meal in visible_meals
            ]
            # Nový riadok dostane všetky tri kľúče jedál rovno od začiatku
            # (rovnaký tvar ako `_build_auto_data`) — inak by chýbajúce kľúče
            # namiesto prázdneho `{}` prekvapili kód, ktorý ich číta priamo.
            current_data = (
                dict(existing_order.data or {})
                if existing_order
                else {meal: {} for meal in MEAL_KEYS}
            )
            missing = [meal for meal in scope if _scoped_is_empty(current_data, [meal])]
            if not missing:
                skipped += 1
                continue

            template_fill = _build_auto_data(
                template, missing, visible_portion_types, target_date=target_date
            )
            filled_any = False
            for meal in missing:
                value = template_fill.get(meal, {})
                if not _scoped_is_empty({meal: value}, [meal]):
                    current_data[meal] = value
                    filled_any = True
            if not filled_any:
                skipped += 1
                continue

            if existing_order is None:
                try:
                    with transaction.atomic():
                        _, auto_created = DailyOrder.objects.get_or_create(
                            prevadzka_id=prevadzka_id,
                            date=target_date,
                            defaults={
                                "user": client,
                                "is_auto": True,
                                "data": current_data,
                            },
                        )
                except IntegrityError:
                    # Concurrent task already created the row; treat as skipped.
                    skipped += 1
                    continue
                if not auto_created:
                    # A manual/other order appeared between preload and now.
                    skipped += 1
                    continue
            else:
                # `is_auto` sa tu zámerne nemení: manuálny riadok (False)
                # ostáva manuálny aj s dopísaným auto-jedlom, plne auto (True)
                # ostáva plne auto.
                existing_order.data = current_data
                existing_order.save(update_fields=["data"])

            created.append(client.email)
            logger.info(
                "Auto-order filled meals=%s for user=%s date=%s (template from %s)",
                missing,
                client.email,
                target_date,
                template.date,
            )
            continue

        auto_data = _build_auto_data(
            template,
            visible_meals,
            visible_portion_types,
            target_date=target_date,
        )

        # Skip if filtered data is empty
        if _is_order_empty(auto_data):
            skipped += 1
            continue

        # Use get_or_create inside an atomic block to be idempotent when the
        # auto-order task is triggered concurrently (e.g. duplicate Celery tasks).
        # Rely on the unique constraint for (prevadzka, date) plus IntegrityError
        # handling to ensure that at most one auto-order row is ultimately created.
        try:
            with transaction.atomic():
                _, auto_created = DailyOrder.objects.get_or_create(
                    prevadzka_id=prevadzka_id,
                    date=target_date,
                    defaults={
                        "user": client,
                        "is_auto": True,
                        "data": auto_data,
                    },
                )
        except IntegrityError:
            # Concurrent task already created the row; treat as skipped.
            skipped += 1
            continue

        if not auto_created:
            # A manual order appeared between the preload query and now.
            skipped += 1
            continue

        created.append(client.email)
        logger.info(
            "Auto-order created for user=%s date=%s (template from %s)",
            client.email,
            target_date,
            template.date,
        )

    logger.info(
        "apply_auto_orders: skipped %d EduPage-driven, %d zatvorených a %d "
        "pozastavených (auto_order_paused) prevádzok on %s",
        skipped_edupage,
        skipped_closed,
        len(paused_prevadzka_ids),
        target_date,
    )
    logger.info(
        "apply_auto_orders finished: date=%s created=%d skipped=%d",
        target_date,
        len(created),
        skipped,
    )
    return {"created": created, "skipped": skipped, "date": str(target_date)}
