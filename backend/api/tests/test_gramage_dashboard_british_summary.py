"""`gramage_summary_only` prevádzky (British School, Cluster C, #531) v
`MealPlanService.gramage_dashboard()`:

- nikdy sa nedostanú do bežnej per-klientskej mriežky (`data["rows"]`,
  `data["vydaje"][...]["routes"][...]["rows"]`) — nemajú menu-šablóny, takže
  gramáž by bola prázdna/neúplná a Menu D/VEGE1/desiata by ticho zmizli,
- namiesto toho dostanú vlastný `vydaj` blok s `summary_only=True` a
  `british_summary` (kusy + MŠ prepočet), postavený priamo z `DailyOrder.data`.
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
    Vydaj,
)
from api.services.meal_plan_service import MealPlanService


def _make_plan(date):
    plan = DailyMealPlan.objects.create(date=date)
    MealPlanItem.objects.create(
        meal_plan=plan,
        template=MealTemplate.objects.create(
            name="Obed",
            category="main_course",
            components=[{"label": "Hlavné jedlo", "grams": "300", "unit": "g"}],
            base_weight_grams="300",
        ),
        category="main_course",
        menu_variant="",
    )
    return plan


def _make_british(target_date):
    celok = Celok.objects.create(nazov="British School")
    block = DeliveryBlock.objects.create(name="Trasa extra", sort_order=2)
    route = DeliveryRoute.objects.create(
        name="British School", block=block, vydaj=Vydaj.C, sort_order=1
    )
    prevadzka = Prevadzka.objects.create(
        celok=celok,
        nazov="British School",
        gramage_summary_only=True,
        delivery_route=route,
    )
    DailyOrder.objects.create(
        prevadzka=prevadzka,
        date=target_date,
        data={
            "breakfast": {"Škôlka": {"menuCounts": {"A": 10}, "diets": {}}},
            "desiata": {"ZŠ 1.stupeň": {"menuCounts": {"A": 5}, "diets": {}}},
            "lunch": {
                "Škôlka": {"menuCounts": {"A": 20, "D": 3}, "diets": {}},
            },
            "olovrant": {"Škôlka": {"menuCounts": {"A": 9}, "diets": {}}},
        },
    )
    return prevadzka


@pytest.mark.django_db
def test_summary_only_prevadzka_excluded_from_normal_rows():
    target_date = datetime.date(2026, 9, 7)
    _make_plan(target_date)
    _make_british(target_date)

    data = MealPlanService.gramage_dashboard(target_date.isoformat())

    assert data["rows"] == []
    assert data["unassigned_rows"] == []


@pytest.mark.django_db
def test_summary_only_prevadzka_gets_its_own_summary_vydaj():
    target_date = datetime.date(2026, 9, 7)
    _make_plan(target_date)
    _make_british(target_date)

    data = MealPlanService.gramage_dashboard(target_date.isoformat())

    british_vydaj = next(v for v in data["vydaje"] if v["key"] == str(Vydaj.C))
    assert british_vydaj["summary_only"] is True
    # Žiadne bežné client rows v tomto vydaji.
    assert all(not route["rows"] for route in british_vydaj["routes"])
    labels = {m["label"]: m for m in british_vydaj["british_summary"]}
    assert labels["Raňajky"]["heads"] == 10
    assert labels["Desiata"]["heads"] == 5
    assert labels["Obed"]["heads"] == 23
    assert labels["Olovrant"]["heads"] == 9


@pytest.mark.django_db
def test_normal_prevadzka_unaffected_by_summary_only_flag():
    target_date = datetime.date(2026, 9, 7)
    _make_plan(target_date)
    _make_british(target_date)
    celok = Celok.objects.create(nazov="MŠ Bežná")
    prevadzka = Prevadzka.objects.create(celok=celok, nazov="MŠ Bežná")
    user = User.objects.create_user(username="bezna@example.com", password="x")
    DailyOrder.objects.create(
        user=user,
        prevadzka=prevadzka,
        date=target_date,
        data={"lunch": {"Škôlka": {"menuCounts": {"": 12}, "diets": {}}}},
    )

    data = MealPlanService.gramage_dashboard(target_date.isoformat())

    assert len(data["rows"]) == 1
    assert data["rows"][0]["client"] == "MŠ Bežná"


@pytest.mark.django_db
def test_no_summary_only_prevadzka_means_no_summary_vydaje():
    target_date = datetime.date(2026, 9, 7)
    _make_plan(target_date)

    data = MealPlanService.gramage_dashboard(target_date.isoformat())

    assert not any(v.get("summary_only") for v in data["vydaje"])
