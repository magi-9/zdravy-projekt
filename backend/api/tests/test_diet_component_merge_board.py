"""`diet_component_merge_board` (#568, flip 10.9.2026) — dáta pre klikací
zoznam "spolu/zvlášť": zložky dňa (raňajky/desiata, obed len Menu A,
olovrant), aktívne diéty a aktuálny "spolu" stav (default, mínus explicitné
"zvlášť" výnimky)."""

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


def test_lists_components_for_all_four_relevant_meals():
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
    # Polievka (11.9.2026) je od hlavného jedla nezávislá voľba v tomto
    # boarde — má vlastný riadok, aj keď v `gramage_table_spec` ostáva
    # zlúčená do riadku obeda (`_merge_soup_into_main_course`).
    assert set(meals_by_key) == {"soup", "main_course", "afternoon_snack"}
    assert meals_by_key["soup"]["components"] == [{"index": 0, "label": "Polievka"}]
    assert meals_by_key["main_course"]["components"] == [
        {"index": 0, "label": "Hlavná časť"},
        {"index": 1, "label": "Príloha"},
    ]
    assert meals_by_key["afternoon_snack"]["components"] == [
        {"index": 0, "label": "Olovrant"}
    ]


def test_soup_and_main_course_are_toggled_independently():
    """Polievka a hlavné jedlo sú v tomto boarde samostatné bunky — diéta
    môže byť "zvlášť" len pri polievke, len pri hlavnom jedle, alebo pri
    oboch, nezávisle."""
    plan = DailyMealPlan.objects.create(date=datetime.date(2026, 9, 25))
    Diet.objects.create(name="Bez lepku")
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
            components=[{"label": "Hlavná časť", "grams": "200", "unit": "g"}],
            base_weight_grams="200",
        ),
        category="main_course",
        menu_variant="A",
    )
    DietComponentMerge.objects.create(
        date=plan.date,
        meal="soup",
        component_index=0,
        diet=Diet.objects.get(name="Bez lepku"),
    )

    board = diet_component_merge_board(plan.date.isoformat())

    assert {
        "meal": "soup",
        "diet_name": "Bez lepku",
        "component_index": 0,
    } not in board["merged"]
    assert {
        "meal": "main_course",
        "diet_name": "Bez lepku",
        "component_index": 0,
    } in board["merged"]


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


def test_all_components_are_merged_by_default_with_no_separation_rows():
    plan = DailyMealPlan.objects.create(date=datetime.date(2026, 9, 24))
    Diet.objects.create(name="Bez lepku")
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

    board = diet_component_merge_board(plan.date.isoformat())

    assert board["merged"] == [
        {"meal": "main_course", "diet_name": "Bez lepku", "component_index": 0}
    ]


def test_explicit_separation_row_excludes_that_cell_from_the_default_merge():
    plan = DailyMealPlan.objects.create(date=datetime.date(2026, 9, 24))
    diet_separated = Diet.objects.create(name="Bez lepku")
    Diet.objects.create(name="Bez laktózy")
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
    DietComponentMerge.objects.create(
        date=plan.date,
        meal=MealCategory.MAIN_COURSE,
        component_index=0,
        diet=diet_separated,
    )

    board = diet_component_merge_board(plan.date.isoformat())

    assert board["merged"] == [
        {"meal": "main_course", "diet_name": "Bez laktózy", "component_index": 0}
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
