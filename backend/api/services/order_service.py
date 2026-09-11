"""Order service – pure business logic for order domain."""

import datetime
from typing import Any, Dict, List, Optional, Tuple

from django.contrib.auth.models import User
from django.utils import timezone

from ..models import Celok, DailyOrder, Holiday, PrevadzkaClosure
from ..order_data import MEAL_KEYS, OrderData
from ..scheduling import expand_closures, is_weekend
from .auto_order_service import _build_auto_data, _is_order_empty
from .prevadzka_service import dostupne_prevadzky

# Okno, v ktorom sa hľadá 5 dní na objednanie. Musí pokryť aj dlhšie voľno
# prevádzky (#490) — dva týždne prázdnin posunú pätku dopredu o desiatky dní.
_PLANNED_WINDOW_DAYS = 120


def _merge_meal_data(target: Dict[str, Any], addition: Dict[str, Any]) -> None:
    """Prirátaj `addition` do `target` (tvar {jedlo: {kategória: {menuCounts, diets}}}).

    Kategórie sa medzi prevádzkami opakujú (Škôlka, Jasle…), takže deň za celok
    je súčet ich počtov — nie zoznam samostatných blokov.
    """
    for meal_key, categories in addition.items():
        if not isinstance(categories, dict):
            continue
        target_meal = target.setdefault(meal_key, {})
        for category, details in categories.items():
            if not isinstance(details, dict):
                continue
            target_category = target_meal.setdefault(category, {})
            for group in ("menuCounts", "diets"):
                counts = details.get(group)
                if not isinstance(counts, dict):
                    continue
                target_counts = target_category.setdefault(group, {})
                for key, value in counts.items():
                    if isinstance(value, bool) or not isinstance(value, int):
                        continue
                    target_counts[key] = target_counts.get(key, 0) + value


class OrderService:
    """Business logic for orders: planned-week calculation, portion counting."""

    # ------------------------------------------------------------------ #
    # Pure helpers (no DB access)
    # ------------------------------------------------------------------ #

    @staticmethod
    def next_workdays(
        start: datetime.date,
        count: int = 5,
        holidays: Optional[set[datetime.date]] = None,
        closed: Optional[set[datetime.date]] = None,
    ) -> List[datetime.date]:
        """Return the next *count* Mon–Fri non-holiday dates starting from *and including* start.

        `closed` sú navyše dni voľna prevádzky (#490/#489). Množiny sa berú
        zvonku (nie z DB ako v `api.scheduling`), aby helper zostal čistý a
        volajúci si mohol načítať oboje jedným dotazom pre celé okno.
        """
        days: List[datetime.date] = []
        d = start
        while len(days) < count:
            if (
                not is_weekend(d)
                and (holidays is None or d not in holidays)
                and (closed is None or d not in closed)
            ):
                days.append(d)
            d += datetime.timedelta(days=1)
        return days

    @staticmethod
    def order_total(data: Dict[str, Any]) -> Tuple[int, Dict[str, int]]:
        """Return (total_portions, {meal: count}) for an order data dict."""
        return OrderData(data).totals()

    @staticmethod
    def monthly_summary(
        user: User,
        year: int,
        month: int,
        through_date: Optional[datetime.date] = None,
    ) -> Dict[str, Any]:
        """Aggregate submitted order counts for a user's month."""
        start = datetime.date(year, month, 1)
        end = (
            datetime.date(year + 1, 1, 1)
            if month == 12
            else datetime.date(year, month + 1, 1)
        )

        today = through_date or timezone.localdate()
        if year == today.year and month == today.month:
            end = min(end, today + datetime.timedelta(days=1))

        menu_counts: Dict[str, int] = {}
        meal_counts: Dict[str, int] = {"breakfast": 0, "lunch": 0, "olovrant": 0}
        total = 0

        # Per prevádzku, nie per login: súhrn za celok musí zahrnúť aj to, čo
        # zadal iný login toho istého celku.
        orders = DailyOrder.objects.filter(
            prevadzka__in=dostupne_prevadzky(user),
            date__gte=start,
            date__lt=end,
        ).only("data")

        for order in orders:
            data = order.data or {}
            order_total, order_meals = OrderService.order_total(data)
            total += order_total
            for meal_key, count in order_meals.items():
                meal_counts[meal_key] = meal_counts.get(meal_key, 0) + count

            for menu, count in OrderData(data).menu_totals().items():
                menu_counts[menu] = menu_counts.get(menu, 0) + count

        items = [
            {"label": f"Menu {menu}", "count": count}
            for menu, count in sorted(menu_counts.items())
        ]
        meal_labels = {
            "breakfast": "Raňajky",
            "lunch": "Obed",
            "olovrant": "Olovrant",
        }
        items.extend(
            {"label": meal_labels[meal], "count": count}
            for meal, count in meal_counts.items()
            if count > 0
        )

        return {
            "year": year,
            "month": month,
            "total": total,
            "menu_counts": menu_counts,
            "meal_counts": meal_counts,
            "items": items,
        }

    # ------------------------------------------------------------------ #
    # Planned-orders business logic
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_planned_orders(
        user: User, visible_meals: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Return data for the 5 upcoming workdays for *user*.

        For days that already have an order the actual totals are included.
        For days without an order the predicted totals from the last
        non-empty template are provided.

        Objednávka patrí prevádzke, nie loginu — deň sa preto skladá zo
        všetkých prevádzok, ku ktorým má login prístup, a karta dňa ukazuje
        súčet za celok. Predikcia beží per prevádzka rovnako ako
        `apply_auto_orders`, inak by celok s piatimi prevádzkami videl
        pätinu toho, čo mu auto-objednávka naozaj vytvorí.

        This method executes a small, constant number of DB queries regardless
        of the number of planned days (no N+1 queries).
        """
        today = timezone.localdate()
        # Fetch all upcoming holidays once (small table) to avoid repeated queries.
        holiday_set: set[datetime.date] = set(
            Holiday.objects.filter(date__gte=today).values_list("date", flat=True)
        )
        # Ako poddotaz, nie materializovaný zoznam — inak by prehľad stál dotaz navyše.
        prevadzky = dostupne_prevadzky(user)

        # Voľno prevádzky (#490): deň zmizne z plánu len keď majú voľno VŠETKY
        # prevádzky loginu — celok s piatimi škôlkami objednáva ďalej, aj keď
        # jedna z nich má prázdniny. Okno je zámerne širšie než 5 dní: dlhé
        # voľno posunie päticu pracovných dní dopredu.
        window_end = today + datetime.timedelta(days=_PLANNED_WINDOW_DAYS)
        closed_by_prevadzka = expand_closures(
            PrevadzkaClosure.objects.filter(
                prevadzka__in=prevadzky, date_from__lte=window_end, date_to__gte=today
            ).values_list("prevadzka_id", "date_from", "date_to"),
            today,
            window_end,
        )
        fully_closed: set[datetime.date] = set()
        # Zoznam id-čiek stojí dotaz navyše, tak ho pýtame len keď vôbec nejaké
        # voľno existuje — bežný login žiadne nemá a prehľad ostáva rovnako lacný.
        if closed_by_prevadzka:
            prevadzka_ids = list(prevadzky.values_list("id", flat=True))
            day_cursor = today
            while day_cursor <= window_end:
                if prevadzka_ids and all(
                    day_cursor in closed_by_prevadzka.get(pid, set())
                    for pid in prevadzka_ids
                ):
                    fully_closed.add(day_cursor)
                day_cursor += datetime.timedelta(days=1)

        workdays = OrderService.next_workdays(today, 5, holiday_set, fully_closed)

        existing: Dict[datetime.date, List[DailyOrder]] = {}
        for order in (
            DailyOrder.objects.filter(prevadzka__in=prevadzky, date__in=workdays)
            .select_related("prevadzka")
            .prefetch_related("prevadzka__visible_portion_types")
        ):
            existing.setdefault(order.date, []).append(order)

        # Najlepšia (posledná neprázdna) šablóna per prevádzka — 1 dotaz, bez N+1.
        # Rovnaké pravidlo ako v `apply_auto_orders`, aby sedel odhad aj výsledok.
        # Prevádzka bez šablóny do odhadu nič nepridá, takže stačia tieto kľúče.
        templates_by_prevadzka: Dict[int, DailyOrder] = {}
        # Predikcia v klientskom prehľade smie ukazovať iba to, čo môže
        # `apply_auto_orders` naozaj vytvoriť. EduPage prevádzky má na starosti
        # scrape a pauznutá prevádzka nesmie pokračovať v starej šablóne.
        # `prevadzka__celok` je vo `select_related` navyše, aby toto porovnanie
        # nestálo samostatný dotaz (viď `_edupage_prevadzka_ids()` v
        # auto_order_service.py, ktorý robí to isté globálne, keď škálovanie
        # na "všetky prevádzky" dáva zmysel).
        for order in (
            DailyOrder.objects.filter(prevadzka__in=prevadzky, date__lt=workdays[0])
            .select_related("prevadzka__celok")
            .prefetch_related("prevadzka__visible_portion_types")
            .order_by("prevadzka_id", "-date")
        ):
            if order.prevadzka_id in templates_by_prevadzka:
                continue
            if (
                order.prevadzka.celok.zdroj_objednavok == Celok.ZdrojObjednavok.EDUPAGE
                or order.prevadzka.auto_order_paused
            ):
                continue
            if not _is_order_empty(order.data or {}):
                templates_by_prevadzka[order.prevadzka_id] = order

        # Prevádzka vie prispieť do odhadu buď historickou šablónou, alebo
        # objednávkou skôr v okne (kaskáda) — oboje je už načítané v pamäti.
        predictable_prevadzka_ids = sorted(
            set(templates_by_prevadzka)
            | {
                order.prevadzka_id
                for day_orders in existing.values()
                for order in day_orders
            }
        )

        def _template_for(
            day: datetime.date, prevadzka_id: int
        ) -> Optional[DailyOrder]:
            """
            Return the best template for a prevádzka on a missing day.

            Checks the in-memory cascade (orders already placed earlier in the
            planned window for that same prevádzka) before falling back to the
            historical template. No additional DB queries are made.
            """
            for prev_day in reversed([d for d in workdays if d < day]):
                for prev in existing.get(prev_day, []):
                    if prev.prevadzka_id != prevadzka_id:
                        continue
                    if not _is_order_empty(prev.data or {}):
                        return prev
            return templates_by_prevadzka.get(prevadzka_id)

        result: List[Dict[str, Any]] = []
        for day in workdays:
            orders = existing.get(day, [])
            if orders:
                total = 0
                meal_count = {meal: 0 for meal in MEAL_KEYS}
                for order in orders:
                    order_total, order_meals = OrderService.order_total(
                        order.data or {}
                    )
                    total += order_total
                    for meal_key, count in order_meals.items():
                        meal_count[meal_key] = meal_count.get(meal_key, 0) + count
                result.append(
                    {
                        "date": str(day),
                        "exists": True,
                        # Deň je „automatický" len keď ho tak dostali všetky
                        # prevádzky — inak doň zasiahol človek.
                        "is_auto": all(o.is_auto for o in orders),
                        "is_empty": total == 0,
                        "totalPortions": total,
                        "mealCount": meal_count,
                        "predictedTotal": 0,
                        "predictedMealCount": {
                            "breakfast": 0,
                            "lunch": 0,
                            "olovrant": 0,
                        },
                    }
                )
                continue

            predicted_data: Dict[str, Any] = {meal: {} for meal in MEAL_KEYS}
            for prevadzka_id in predictable_prevadzka_ids:
                # Prevádzka s voľnom v tento deň do odhadu neprispieva — inak by
                # klient videl predikciu porcií, ktoré sa aj tak neuvaria.
                if day in closed_by_prevadzka.get(prevadzka_id, set()):
                    continue
                tmpl = _template_for(day, prevadzka_id)
                if tmpl is None:
                    continue
                allowed_meals = visible_meals
                if allowed_meals is None:
                    allowed_meals = list(
                        getattr(tmpl.prevadzka, "visible_meals", []) or []
                    )
                visible_portion_types = [
                    portion_type.name
                    for portion_type in tmpl.prevadzka.visible_portion_types.all()
                    if portion_type.is_active
                ]
                _merge_meal_data(
                    predicted_data,
                    _build_auto_data(tmpl, allowed_meals, visible_portion_types),
                )
            predicted_total, predicted_meal_count = OrderService.order_total(
                predicted_data
            )
            result.append(
                {
                    "date": str(day),
                    "exists": False,
                    "is_auto": None,
                    "is_empty": None,
                    "totalPortions": 0,
                    "mealCount": {"breakfast": 0, "lunch": 0, "olovrant": 0},
                    "predictedTotal": predicted_total,
                    "predictedMealCount": predicted_meal_count,
                    "predictedData": predicted_data,
                }
            )

        return result
