"""Kusový sumár pre prevádzky bez gramážových menu-šablón (British School,
Cluster C, #531).

Na rozdiel od `MealPlanService.gramage_dashboard()` (per-klientská mriežka s
gramami, riadená týždennými menu-šablónami `DailyMealPlan`) tento modul číta
priamo `DailyOrder.data` — žiadne šablóny, žiadna gramáž, len počty hláv a ich
prepočet na MŠ porcie cez katalógový `PortionType.coefficient` (rovnaká
logika ako `gramage_table_spec._cluster_ms_totals`, len bez závislosti na
`col_groups`/`sub_rows`).

Prevádzka sa označí `Prevadzka.gramage_summary_only=True` (British seed) —
`MealPlanService.gramage_dashboard()` také prevádzky vynechá z bežnej
mriežky a namiesto toho sem vloží výstup tejto funkcie.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

# Poradie pásiem dňa — chronologické, nezávislé od poradia kľúčov v
# `order.data`. "desiata" je British-špecifický meal_key (#British Cluster C,
# NIE "snack" — ten je legacy alias pre Olovrant, viď `api.tasks._EXTRA_MEAL_KEYS`).
_MEAL_BANDS: tuple[tuple[str, str], ...] = (
    ("breakfast", "Raňajky"),
    ("desiata", "Desiata"),
    ("lunch", "Obed"),
    ("olovrant", "Olovrant"),
)

# Stabilné poradie menu variantov v rozpise "Obed" — bežné písmená najprv,
# British špecifiká (Menu D, VEGE1) za nimi. Neznáme varianty (budúca škola)
# padnú na koniec, zoradené abecedne, aby poradie ostalo deterministické.
_MENU_VARIANT_ORDER: tuple[str, ...] = ("A", "B", "C", "D", "VEGE1")

_DEFAULT_COEFFICIENT = Decimal("1")


def _as_decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _menu_sort_key(variant: str) -> tuple[int, str]:
    try:
        return (_MENU_VARIANT_ORDER.index(variant), "")
    except ValueError:
        return (len(_MENU_VARIANT_ORDER), variant)


def meal_items_from_order_data(
    order_data: dict[str, Any], portion_coefficients: dict[str, Decimal]
) -> list[dict[str, Any]]:
    """`order.data` → zoznam pásiem dňa s kusmi + MŠ prepočtom.

    `portion_coefficients` = {PortionType.name: coefficient}; neznáma porcia
    dostane koeficient 1 (rovnaký fallback ako `MealPlanService.gramage_dashboard`,
    #532). Meal, ktorý daný deň vôbec nemá dáta, sa do výstupu nedostane —
    inak by tabuľka fabrikovala jedlo, ktoré škola ten deň neobjednávala.

    "Obed" (`lunch`) navyše nesie rozpis `menus` po menu variantoch
    (`menuCounts` kľúče — A/B/C/D/VEGE1 a čokoľvek ďalšie), len keď je
    variantov viac než jeden — jediný variant by len duplikoval riadok Obed.
    Diétne počty (`diets`) sa do `heads` NEZAPOČÍTAVAJÚ navyše — sú drill-down
    tej istej hlavičky (`effective_menu`/`menu_counts` v `edupage_scraper.py`
    ich už zarátal), nie samostatné porcie.
    """
    items: list[dict[str, Any]] = []
    for meal_key, label in _MEAL_BANDS:
        meal_data = order_data.get(meal_key)
        if not meal_data:
            continue
        heads = Decimal("0")
        total = Decimal("0")
        menu_totals: dict[str, tuple[Decimal, Decimal]] = {}
        for portion_name, counts in meal_data.items():
            coeff = portion_coefficients.get(portion_name, _DEFAULT_COEFFICIENT)
            menu_counts = (counts or {}).get("menuCounts") or {}
            for variant, raw_count in menu_counts.items():
                count = _as_decimal(raw_count)
                if count <= 0:
                    continue
                ms = count * coeff
                heads += count
                total += ms
                prev_heads, prev_ms = menu_totals.get(
                    variant, (Decimal("0"), Decimal("0"))
                )
                menu_totals[variant] = (prev_heads + count, prev_ms + ms)
        item: dict[str, Any] = {"label": label, "heads": heads, "total": total}
        if meal_key == "lunch" and len(menu_totals) > 1:
            item["menus"] = [
                {
                    "label": f"Menu {variant}",
                    "heads": menu_heads,
                    "total": menu_total,
                }
                for variant, (menu_heads, menu_total) in sorted(
                    menu_totals.items(), key=lambda kv: _menu_sort_key(kv[0])
                )
            ]
        items.append(item)
    return items


def build_gramage_summary_only_clusters(date_str: str) -> list[dict[str, Any]]:
    """Jeden záznam na `gramage_summary_only` prevádzku, ktorá má ten deň
    objednávku — pripravené na vloženie do `MealPlanService.gramage_dashboard()`
    výstupu ako samostatný (kusový) `vydaj` blok.
    """
    from ..models import DailyOrder, PortionType, Prevadzka, Vydaj

    prevadzky = list(
        Prevadzka.objects.filter(
            gramage_summary_only=True, is_active=True
        ).select_related("delivery_route__block")
    )
    if not prevadzky:
        return []

    portion_coefficients = {
        pt.name: pt.coefficient for pt in PortionType.objects.filter(is_active=True)
    }
    orders_by_prevadzka = {
        order.prevadzka_id: order
        for order in DailyOrder.objects.filter(date=date_str, prevadzka__in=prevadzky)
    }

    clusters: list[dict[str, Any]] = []
    for prevadzka in prevadzky:
        order = orders_by_prevadzka.get(prevadzka.id)
        if order is None or not isinstance(order.data, dict) or not order.data:
            continue
        meals = meal_items_from_order_data(order.data, portion_coefficients)
        if not meals:
            continue
        route = prevadzka.delivery_route
        clusters.append(
            {
                "vydaj_key": str(route.vydaj) if route else str(Vydaj.A),
                "route_name": route.name if route else prevadzka.nazov,
                "prevadzka_id": prevadzka.id,
                "prevadzka_name": prevadzka.nazov,
                "meals": meals,
            }
        )
    return clusters
