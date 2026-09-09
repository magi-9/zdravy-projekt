"""DietPackingPreference: plošné (naprieč prevádzkami) nastavenie „táto diéta
sa dnes balí zvlášť" (default = spolu), viď zadanie 9.9.2026 — checkbox v
admin gramážnej tabuľke, default odškrtnuté = spolu.
"""

import datetime

import pytest
from django.db import IntegrityError

from api.models import Diet, DietPackingPreference
from api.services.meal_plan_service import resolve_diet_packing_preferences

pytestmark = pytest.mark.django_db


def test_default_is_pack_together():
    diet = Diet.objects.create(name="No Milk")
    pref = DietPackingPreference.objects.create(
        diet=diet, date=datetime.date(2026, 9, 10)
    )
    assert pref.pack_separately is False


def test_unique_per_diet_and_date():
    diet = Diet.objects.create(name="No Milk")
    DietPackingPreference.objects.create(
        diet=diet, date=datetime.date(2026, 9, 10), pack_separately=True
    )
    with pytest.raises(IntegrityError):
        DietPackingPreference.objects.create(
            diet=diet, date=datetime.date(2026, 9, 10), pack_separately=False
        )


def test_same_diet_different_day_is_allowed():
    diet = Diet.objects.create(name="No Milk")
    DietPackingPreference.objects.create(
        diet=diet, date=datetime.date(2026, 9, 10), pack_separately=True
    )
    DietPackingPreference.objects.create(
        diet=diet, date=datetime.date(2026, 9, 11), pack_separately=False
    )
    assert DietPackingPreference.objects.count() == 2


class TestResolveDietPackingPreferences:
    """`resolve_diet_packing_preferences(date)` — plošný stav pre daný deň,
    vrátane dedenia na kombinované diéty cez `Diet.base_diets`."""

    def test_no_preferences_means_nothing_separate(self):
        Diet.objects.create(name="No Milk")
        result = resolve_diet_packing_preferences(datetime.date(2026, 9, 10))
        assert result == {}

    def test_flagged_diet_is_separate(self):
        diet = Diet.objects.create(name="No Milk")
        DietPackingPreference.objects.create(
            diet=diet, date=datetime.date(2026, 9, 10), pack_separately=True
        )
        result = resolve_diet_packing_preferences(datetime.date(2026, 9, 10))
        assert result == {"No Milk": True}

    def test_only_applies_on_its_own_date(self):
        diet = Diet.objects.create(name="No Milk")
        DietPackingPreference.objects.create(
            diet=diet, date=datetime.date(2026, 9, 10), pack_separately=True
        )
        result = resolve_diet_packing_preferences(datetime.date(2026, 9, 11))
        assert result == {}

    def test_combined_diet_inherits_separate_flag_from_base_diet(self):
        """Zaškrtnutie 'No Milk' ako zvlášť musí strhnúť aj kombinácie, ktoré
        No Milk obsahujú (napr. 'Diéta X + No Milk')."""
        nomilk = Diet.objects.create(name="No Milk")
        combo = Diet.objects.create(name="Diéta X + No Milk")
        combo.base_diets.add(nomilk)
        DietPackingPreference.objects.create(
            diet=nomilk, date=datetime.date(2026, 9, 10), pack_separately=True
        )
        result = resolve_diet_packing_preferences(datetime.date(2026, 9, 10))
        assert result == {"No Milk": True, "Diéta X + No Milk": True}

    def test_unrelated_combined_diet_is_not_affected(self):
        nomilk = Diet.objects.create(name="No Milk")
        other = Diet.objects.create(name="No Gluten")
        combo = Diet.objects.create(name="No Gluten + Vege")
        combo.base_diets.add(other)
        DietPackingPreference.objects.create(
            diet=nomilk, date=datetime.date(2026, 9, 10), pack_separately=True
        )
        result = resolve_diet_packing_preferences(datetime.date(2026, 9, 10))
        assert result == {"No Milk": True}
