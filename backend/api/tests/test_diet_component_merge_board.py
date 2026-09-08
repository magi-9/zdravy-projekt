"""`diet_component_merge_board` (#568) — dáta pre klikací zoznam "spolu/
zvlášť": zložky dňa (raňajky/desiata, obed len Menu A, olovrant), aktívne
diéty a aktuálny stav zlúčenia."""

import datetime

import pytest
from django.core.management import call_command

from api.models import (
    DailyMealPlan,
    Diet,
    DietComponentMerge,
    MealCategory,
    MealPlanItem,
    MealTemplate,
)
from api.services.meal_plan_service import diet_component_merge_board

pytestmark = pytest.mark.django_db


def test_no_meal_plan_returns_no_meals_but_still_lists_diets():
    call_command("init_reference_data")
    board = diet_component_merge_board("2026-09-20")
    assert board["meals"] == []
    assert board["merged"] == []
    assert any(d["name"] == "NO MILK" for d in board["diets"])


def test_lists_components_for_the_three_relevant_meals_only():
    plan = DailyMealPlan.objects.create(date=datetime.date(2026, 9, 21))
    MealPlanItem.objects.create(
        meal_plan=plan,
        template=MealTemplate.objects.create(
            name="Polievka",
            category="soup",
            components=[{"label": "Polievka", "grams": "200", "unit": "g"}],
            base_weight_grams="200",
        ),
        category="soup",
    )
    MealPlanItem.objects.create(
        meal_plan=plan,
        template=MealTemplate.objects.create(
            name="Obed A",
            category="main_course",
            components=[
                {"label": "Hlavná časť", "grams": "200", "unit": "g"},
                {"label": "Príloha", "grams": "100", "unit": "g"},
            ],
            base_weight_grams="300",
        ),
        category="main_course",
        menu_variant="A",
    )
    MealPlanItem.objects.create(
        meal_plan=plan,
        template=MealTemplate.objects.create(
            name="Olovrant",
            category="afternoon_snack",
            components=[{"label": "Olovrant", "grams": "150", "unit": "g"}],
            base_weight_grams="150",
        ),
        category="afternoon_snack",
    )

    board = diet_component_merge_board(plan.date.isoformat())

    meals_by_key = {m["meal"]: m for m in board["meals"]}
    # Polievka nie je súčasťou tohto boardu (patrí pod obed, nie je vlastná
    # zložka zo šéfkuchárskeho pohľadu).
    assert set(meals_by_key) == {"main_course", "afternoon_snack"}
    assert meals_by_key["main_course"]["components"] == [
        {"index": 0, "label": "Hlavná časť"},
        {"index": 1, "label": "Príloha"},
    ]
    assert meals_by_key["afternoon_snack"]["components"] == [
        {"index": 0, "label": "Olovrant"}
    ]


def test_only_menu_a_is_considered_for_main_course():
    plan = DailyMealPlan.objects.create(date=datetime.date(2026, 9, 22))
    MealPlanItem.objects.create(
        meal_plan=plan,
        template=MealTemplate.objects.create(
            name="Obed B",
            category="main_course",
            components=[{"label": "Iné jedlo", "grams": "250", "unit": "g"}],
            base_weight_grams="250",
        ),
        category="main_course",
        menu_variant="B",
    )

    board = diet_component_merge_board(plan.date.isoformat())

    assert board["meals"] == []


def test_diet_specific_meal_plan_items_are_ignored():
    """Vlastný diétny template (item.diet_id) nie je "štandardné" Menu A —
    board vychádza z bezdiétneho riadku, nie z diétneho."""
    diet = Diet.objects.create(name="Bez lepku")
    plan = DailyMealPlan.objects.create(date=datetime.date(2026, 9, 23))
    MealPlanItem.objects.create(
        meal_plan=plan,
        template=MealTemplate.objects.create(
            name="Obed A",
            category="main_course",
            components=[{"label": "Hlavná časť", "grams": "200", "unit": "g"}],
            base_weight_grams="200",
        ),
        category="main_course",
        menu_variant="A",
    )
    MealPlanItem.objects.create(
        meal_plan=plan,
        template=MealTemplate.objects.create(
            name="Obed A bezlepkový",
            category="main_course",
            components=[
                {"label": "Bezlepková hlavná časť", "grams": "200", "unit": "g"}
            ],
            base_weight_grams="200",
        ),
        category="main_course",
        menu_variant="A",
        diet=diet,
    )

    board = diet_component_merge_board(plan.date.isoformat())

    [main] = [m for m in board["meals"] if m["meal"] == "main_course"]
    assert main["components"] == [{"index": 0, "label": "Hlavná časť"}]


def test_merged_state_reflects_existing_diet_component_merge_rows():
    plan = DailyMealPlan.objects.create(date=datetime.date(2026, 9, 24))
    diet = Diet.objects.create(name="Bez lepku")
    DietComponentMerge.objects.create(
        date=plan.date,
        meal=MealCategory.MAIN_COURSE,
        component_index=0,
        diet=diet,
    )

    board = diet_component_merge_board(plan.date.isoformat())

    assert board["merged"] == [
        {"meal": "main_course", "diet_name": "Bez lepku", "component_index": 0}
    ]


def test_breakfast_components_collapse_like_the_gramage_table_does():
    plan = DailyMealPlan.objects.create(date=datetime.date(2026, 9, 25))
    MealPlanItem.objects.create(
        meal_plan=plan,
        template=MealTemplate.objects.create(
            name="Raňajky",
            category="breakfast_snack",
            components=[
                {"label": "Hlavná zložka", "grams": "50", "unit": "g"},
                {"label": "Extra zložka 1", "grams": "15", "unit": "g"},
            ],
            base_weight_grams="65",
        ),
        category="breakfast_snack",
    )

    board = diet_component_merge_board(plan.date.isoformat())

    [breakfast] = [m for m in board["meals"] if m["meal"] == "breakfast_snack"]
    assert breakfast["components"] == [{"index": 0, "label": "Raňajky-desiata spolu"}]
