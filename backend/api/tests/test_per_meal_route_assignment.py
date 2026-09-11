"""Ktorá prevádzka sa objaví v ktorej per-jedlo tabuľke
(#dashboard-per-meal-routes, 10.9.2026):

- Prevádzka bez daného jedla v `visible_meals` sa v jeho tabuľke nemá
  objaviť VÔBEC — ani ako "Nepriradená".
- "Olovrant s obedom" (`Prevadzka.olovrant_s_obedom`) nemá vlastnú
  olovrantovú trasu/tabuľku — jeho olovrant sa objaví v OBEDOVEJ tabuľke
  ako dodatočný stĺpec, ostatné (bez príznaku) prevádzky ho tam nemajú
  vyplnený, aj keď stĺpec existuje.
"""

import datetime
import importlib

import pytest
from django.contrib.auth.models import User

from api.models import (
    Celok,
    DailyMealPlan,
    DailyOrder,
    DeliveryBlock,
    DeliveryRoute,
    MealPlanItem,
    MealTemplate,
    Prevadzka,
)
from api.services.meal_plan_service import MealPlanService

pytestmark = pytest.mark.django_db

MAIN_COURSE_COMPONENTS = [{"label": "Hlavná časť", "grams": "200", "unit": "g"}]
SNACK_COMPONENTS = [{"label": "Ovocie", "grams": "100", "unit": "g"}]


def _plan(date):
    plan = DailyMealPlan.objects.create(date=date)
    MealPlanItem.objects.create(
        meal_plan=plan,
        template=MealTemplate.objects.create(
            name="Obed A",
            category="main_course",
            components=MAIN_COURSE_COMPONENTS,
            base_weight_grams="200",
        ),
        category="main_course",
        menu_variant="A",
    )
    MealPlanItem.objects.create(
        meal_plan=plan,
        template=MealTemplate.objects.create(
            name="Ovocie",
            category="afternoon_snack",
            components=SNACK_COMPONENTS,
            base_weight_grams="100",
        ),
        category="afternoon_snack",
        menu_variant="",
    )
    return plan


def _prevadzka(name, visible_meals=None, **kwargs):
    celok = Celok.objects.create(nazov=name)
    prevadzka = Prevadzka.objects.create(celok=celok, nazov=name, **kwargs)
    # `on_prevadzka_saved` signál pri vytvorení prepíše visible_meals na
    # canonical default bez ohľadu na to, čo sa poslalo do `.create()` —
    # treba ho nastaviť až samostatným save-om potom.
    if visible_meals is not None:
        prevadzka.visible_meals = visible_meals
        prevadzka.save(update_fields=["visible_meals"])
    return prevadzka


def _route(meal_type="lunch"):
    block = DeliveryBlock.objects.create(
        name=f"Trasa {meal_type}", meal_type=meal_type, sort_order=1
    )
    return DeliveryRoute.objects.create(name="Trasa 1", block=block, sort_order=1)


def _order(prevadzka, date, lunch=6, olovrant=0):
    data = {"lunch": {"Škôlka": {"menuCounts": {"A": lunch}, "diets": {}}}}
    if olovrant:
        data["olovrant"] = {"Škôlka": {"menuCounts": {"A": olovrant}, "diets": {}}}
    return DailyOrder.objects.create(
        user=User.objects.create_user(
            username=f"{prevadzka.nazov}@example.com", password="x"
        ),
        prevadzka=prevadzka,
        date=date,
        data=data,
    )


def test_prevadzka_without_olovrant_in_visible_meals_is_absent_from_that_table():
    plan = _plan(datetime.date(2026, 9, 20))
    route = _route("lunch")
    prevadzka = _prevadzka("MŠ Bez olovrantu", visible_meals=["breakfast", "lunch"])
    prevadzka.delivery_route_lunch = route
    prevadzka.save(update_fields=["delivery_route_lunch"])
    _order(prevadzka, plan.date)

    data = MealPlanService.gramage_dashboard(plan.date.isoformat())

    assert data["vydaje_by_meal"]["olovrant"] == []
    assert data["unassigned_rows_by_meal"]["olovrant"] == []
    # Obedová tabuľka ju má normálne (visible_meals ju tam nechýba).
    lunch_rows = [
        row
        for vydaj in data["vydaje_by_meal"]["lunch"]
        for route_ in vydaj["routes"]
        for row in route_["rows"]
    ]
    assert len(lunch_rows) == 1


def test_olovrant_s_obedom_prevadzka_is_absent_from_the_olovrant_table():
    plan = _plan(datetime.date(2026, 9, 21))
    route = _route("lunch")
    prevadzka = _prevadzka("MŠ Žltá", olovrant_s_obedom=True)
    prevadzka.delivery_route_lunch = route
    prevadzka.save(update_fields=["delivery_route_lunch"])
    _order(prevadzka, plan.date, lunch=6, olovrant=4)

    data = MealPlanService.gramage_dashboard(plan.date.isoformat())

    assert data["vydaje_by_meal"]["olovrant"] == []
    assert data["unassigned_rows_by_meal"]["olovrant"] == []


def test_olovrant_s_obedom_snack_shows_up_inside_the_lunch_row():
    plan = _plan(datetime.date(2026, 9, 22))
    route = _route("lunch")
    prevadzka = _prevadzka("MŠ Žltá", olovrant_s_obedom=True)
    prevadzka.delivery_route_lunch = route
    prevadzka.save(update_fields=["delivery_route_lunch"])
    _order(prevadzka, plan.date, lunch=6, olovrant=4)

    data = MealPlanService.gramage_dashboard(plan.date.isoformat())
    row = data["vydaje_by_meal"]["lunch"][0]["routes"][0]["rows"][0]

    meals_present = {sr["meal"] for sr in row["sub_rows"]}
    assert "afternoon_snack" in meals_present
    assert "main_course" in meals_present
    assert row["snack_with_lunch"] is True


def test_other_prevadzky_lunch_row_has_no_olovrant_contribution():
    """Bez `olovrant_s_obedom` sa olovrant do obedovej tabuľky nedostane,
    aj keby si ho tá istá prevádzka objednala — patrí do samostatnej
    olovrantovej tabuľky."""
    plan = _plan(datetime.date(2026, 9, 23))
    lunch_route = _route("lunch")
    olovrant_route = _route("olovrant")
    prevadzka = _prevadzka("MŠ Normálna")
    prevadzka.delivery_route_lunch = lunch_route
    prevadzka.delivery_route_olovrant = olovrant_route
    prevadzka.save(update_fields=["delivery_route_lunch", "delivery_route_olovrant"])
    _order(prevadzka, plan.date, lunch=6, olovrant=4)

    data = MealPlanService.gramage_dashboard(plan.date.isoformat())
    lunch_row = data["vydaje_by_meal"]["lunch"][0]["routes"][0]["rows"][0]
    olovrant_row = data["vydaje_by_meal"]["olovrant"][0]["routes"][0]["rows"][0]

    assert {sr["meal"] for sr in lunch_row["sub_rows"]} == {"main_course"}
    assert {sr["meal"] for sr in olovrant_row["sub_rows"]} == {"afternoon_snack"}


def test_deploy_backfill_copies_lunch_route_only_to_eligible_empty_meal_routes():
    """Nové per-meal trasy zdedia obed iba kde to dáva logistický zmysel."""
    lunch_route = _route("lunch")
    custom_breakfast_route = _route("breakfast")
    normal = _prevadzka("MŠ Normálna", visible_meals=["breakfast", "lunch", "olovrant"])
    normal.delivery_route_lunch = lunch_route
    normal.delivery_sort_order_lunch = 7
    normal.save(update_fields=["delivery_route_lunch", "delivery_sort_order_lunch"])

    yellow = _prevadzka(
        "MŠ Žltá migrácia",
        visible_meals=["breakfast", "lunch", "olovrant"],
        olovrant_s_obedom=True,
    )
    yellow.delivery_route_lunch = lunch_route
    yellow.delivery_sort_order_lunch = 8
    yellow.save(update_fields=["delivery_route_lunch", "delivery_sort_order_lunch"])

    custom = _prevadzka("MŠ Ručná", visible_meals=["breakfast", "lunch"])
    custom.delivery_route_lunch = lunch_route
    custom.delivery_sort_order_lunch = 9
    custom.delivery_route_breakfast = custom_breakfast_route
    custom.delivery_sort_order_breakfast = 3
    custom.save(
        update_fields=[
            "delivery_route_lunch",
            "delivery_sort_order_lunch",
            "delivery_route_breakfast",
            "delivery_sort_order_breakfast",
        ]
    )

    migration = importlib.import_module(
        "api.migrations.0113_backfill_per_meal_routes_from_lunch"
    )
    migration.copy_lunch_route_to_eligible_meals(
        importlib.import_module("django.apps").apps, None
    )

    normal.refresh_from_db()
    yellow.refresh_from_db()
    custom.refresh_from_db()
    assert normal.delivery_route_breakfast_id == lunch_route.id
    assert normal.delivery_sort_order_breakfast == 7
    assert normal.delivery_route_olovrant_id == lunch_route.id
    assert normal.delivery_sort_order_olovrant == 7
    assert yellow.delivery_route_breakfast_id == lunch_route.id
    assert yellow.delivery_route_olovrant_id is None
    assert custom.delivery_route_breakfast_id == custom_breakfast_route.id
    assert custom.delivery_sort_order_breakfast == 3
    assert custom.delivery_route_olovrant_id is None


def test_deploy_backfill_0113_pointed_breakfast_and_olovrant_at_the_lunch_route_itself():
    """0113 nastavila `delivery_route_breakfast_id = delivery_route_lunch_id` —
    teda tú ISTÚ trasu, ktorej blok má `meal_type="lunch"`. Prevádzka tak
    zmizla z raňajkovej obrazovky úplne: nie je v žiadnom raňajkovom bloku
    (trasa patrí obedu) a nie je ani medzi "Nepriradenými" (pole nie je NULL).
    0114 to opraví presmerovaním na skutočnú raňajkovú/olovrantovú trasu."""
    lunch_route = _route("lunch")

    broken = _prevadzka("MŠ Rozbitá", visible_meals=["breakfast", "lunch", "olovrant"])
    broken.delivery_route_lunch = lunch_route
    broken.delivery_sort_order_lunch = 4
    # Presne stav po chybnej 0113: breakfast/olovrant ukazuje na obedovú trasu.
    broken.delivery_route_breakfast = lunch_route
    broken.delivery_sort_order_breakfast = 4
    broken.delivery_route_olovrant = lunch_route
    broken.delivery_sort_order_olovrant = 4
    broken.save(
        update_fields=[
            "delivery_route_lunch",
            "delivery_sort_order_lunch",
            "delivery_route_breakfast",
            "delivery_sort_order_breakfast",
            "delivery_route_olovrant",
            "delivery_sort_order_olovrant",
        ]
    )

    # Druhá prevádzka na tej istej (rozbitej) obedovej trase — obe majú
    # skončiť na TEJ ISTEJ novej raňajkovej trase, nie na dvoch rôznych.
    also_broken = _prevadzka("MŠ Tiež rozbitá", visible_meals=["breakfast", "lunch"])
    also_broken.delivery_route_lunch = lunch_route
    also_broken.delivery_route_breakfast = lunch_route
    also_broken.save(update_fields=["delivery_route_lunch", "delivery_route_breakfast"])

    # Táto prevádzka má breakfast trasu už správne (nie rovnakú ako lunch) —
    # migrácia ju nemá ani sa dotknúť.
    custom_breakfast_route = _route("breakfast")
    already_fine = _prevadzka("MŠ Fajn", visible_meals=["breakfast", "lunch"])
    already_fine.delivery_route_lunch = lunch_route
    already_fine.delivery_route_breakfast = custom_breakfast_route
    already_fine.save(
        update_fields=["delivery_route_lunch", "delivery_route_breakfast"]
    )

    migration = importlib.import_module(
        "api.migrations.0114_fix_meal_routes_pointing_at_lunch_route"
    )
    migration.repoint_meal_routes_off_the_lunch_route(
        importlib.import_module("django.apps").apps, None
    )

    broken.refresh_from_db()
    also_broken.refresh_from_db()
    already_fine.refresh_from_db()

    # Nová trasa je vlastná raňajkám/olovrantu, nie tá istá ako obed.
    assert broken.delivery_route_breakfast_id != lunch_route.id
    assert broken.delivery_route_olovrant_id != lunch_route.id
    new_breakfast_route = broken.delivery_route_breakfast
    new_olovrant_route = broken.delivery_route_olovrant
    assert new_breakfast_route.block.meal_type == "breakfast"
    assert new_olovrant_route.block.meal_type == "olovrant"
    # Bez rozlíšenia clustrov — vždy jeden, aby sa tabuľka nikdy nedelila.
    assert new_breakfast_route.vydaj == "A"
    assert new_olovrant_route.vydaj == "A"
    # Meno trasy (vodič/rozvoz) sa zachová, len sa presunie pod správne jedlo.
    assert new_breakfast_route.name == lunch_route.name
    # Poradie sa nemení, len sa opravuje trasa, na ktorú ukazuje.
    assert broken.delivery_sort_order_breakfast == 4

    # Obe prevádzky z tej istej rozbitej obedovej trasy skončia na tej istej
    # novej raňajkovej trase — žiadna duplicitná trasa navyše.
    assert also_broken.delivery_route_breakfast_id == new_breakfast_route.id

    # Už správne nastavená prevádzka ostáva netknutá.
    assert already_fine.delivery_route_breakfast_id == custom_breakfast_route.id
