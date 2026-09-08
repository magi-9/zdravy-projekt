"""`resolve_diet_component_merges` (#568) — číta `DietComponentMerge` pre
daný deň do lookup tvaru, ktorý `gramage_dashboard` priamo použije."""

import datetime

import pytest

from api.models import Diet, DietComponentMerge, MealCategory
from api.services.meal_plan_service import resolve_diet_component_merges

pytestmark = pytest.mark.django_db


def test_no_rows_for_the_day_returns_empty_dict():
    assert resolve_diet_component_merges("2026-09-10") == {}


def test_groups_component_indices_by_meal_and_diet_name():
    diet = Diet.objects.create(name="Bez lepku")
    DietComponentMerge.objects.create(
        date=datetime.date(2026, 9, 10),
        meal=MealCategory.MAIN_COURSE,
        component_index=0,
        diet=diet,
    )
    DietComponentMerge.objects.create(
        date=datetime.date(2026, 9, 10),
        meal=MealCategory.MAIN_COURSE,
        component_index=1,
        diet=diet,
    )

    merges = resolve_diet_component_merges("2026-09-10")

    assert merges == {("main_course", "Bez lepku"): {0, 1}}


def test_different_diets_and_meals_stay_in_separate_buckets():
    diet_a = Diet.objects.create(name="Bez lepku")
    diet_b = Diet.objects.create(name="Bez laktózy")
    date = datetime.date(2026, 9, 10)
    DietComponentMerge.objects.create(
        date=date, meal=MealCategory.MAIN_COURSE, component_index=0, diet=diet_a
    )
    DietComponentMerge.objects.create(
        date=date, meal=MealCategory.BREAKFAST_SNACK, component_index=0, diet=diet_a
    )
    DietComponentMerge.objects.create(
        date=date, meal=MealCategory.MAIN_COURSE, component_index=0, diet=diet_b
    )

    merges = resolve_diet_component_merges("2026-09-10")

    assert merges == {
        ("main_course", "Bez lepku"): {0},
        ("breakfast_snack", "Bez lepku"): {0},
        ("main_course", "Bez laktózy"): {0},
    }


def test_rows_from_other_days_are_excluded():
    diet = Diet.objects.create(name="Bez lepku")
    DietComponentMerge.objects.create(
        date=datetime.date(2026, 9, 11),
        meal=MealCategory.MAIN_COURSE,
        component_index=0,
        diet=diet,
    )

    assert resolve_diet_component_merges("2026-09-10") == {}
