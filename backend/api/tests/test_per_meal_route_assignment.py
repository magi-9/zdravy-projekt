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
