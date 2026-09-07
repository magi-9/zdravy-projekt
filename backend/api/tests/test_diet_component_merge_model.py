"""Model `DietComponentMerge` (#568) — zamyká uniqueness a default sémantiku
"existencia riadku = spolu, chýbajúci riadok = zvlášť".
"""

import datetime

import pytest
from django.db import IntegrityError

from api.models import Diet, DietComponentMerge, MealCategory

pytestmark = pytest.mark.django_db


def _create(diet, **overrides):
    defaults = {
        "date": datetime.date(2026, 9, 10),
        "meal": MealCategory.MAIN_COURSE,
        "component_index": 0,
        "component_label": "Hlavná časť",
        "diet": diet,
    }
    defaults.update(overrides)
    return DietComponentMerge.objects.create(**defaults)


def test_create_merge_row_for_a_diet_component():
    diet = Diet.objects.create(name="Bez lepku")
    merge = _create(diet)
    merge.refresh_from_db()
    assert merge.meal == MealCategory.MAIN_COURSE
    assert merge.component_index == 0
    assert merge.component_label == "Hlavná časť"


def test_same_slot_for_the_same_diet_twice_is_rejected():
    diet = Diet.objects.create(name="Bez lepku")
    _create(diet)
    with pytest.raises(IntegrityError):
        _create(diet)


def test_same_component_index_for_two_different_diets_is_allowed():
    diet_a = Diet.objects.create(name="Bez lepku")
    diet_b = Diet.objects.create(name="Bez laktózy")
    _create(diet_a)
    _create(diet_b)
    assert DietComponentMerge.objects.count() == 2


def test_same_diet_across_different_days_is_allowed():
    diet = Diet.objects.create(name="Bez lepku")
    _create(diet, date=datetime.date(2026, 9, 10))
    _create(diet, date=datetime.date(2026, 9, 11))
    assert DietComponentMerge.objects.count() == 2


def test_same_diet_different_component_index_same_day_is_allowed():
    diet = Diet.objects.create(name="Bez lepku")
    _create(diet, component_index=0)
    _create(diet, component_index=1)
    assert DietComponentMerge.objects.count() == 2


def test_diet_deletion_cascades_to_its_merge_rows():
    diet = Diet.objects.create(name="Bez lepku")
    _create(diet)
    diet.delete()
    assert DietComponentMerge.objects.count() == 0
