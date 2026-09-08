"""Kaskáda "spolu/zvlášť" pre kombinované diéty (#568 nadväzba).

Admin najprv odklikáva jednozložkové (základné) diéty; kombinovaná diéta
(`Diet.base_diets`) sa podľa nich riadi:
- aspoň jedna základná zložka "zvlášť" → kombinácia je automaticky "zvlášť"
  (aj keď predtým bola explicitne "spolu" — kaskáda ju zruší),
- žiadna základná zložka "spolu" sama o sebe kombináciu na "spolu"
  neprepína — to musí admin urobiť sám, až keď sú "spolu" všetky.
"""

import datetime

import pytest

from api.models import Diet, DietComponentMerge, MealCategory
from api.services.meal_plan_service import apply_diet_component_merge_toggle

pytestmark = pytest.mark.django_db

DATE = datetime.date(2026, 9, 10)
MEAL = MealCategory.MAIN_COURSE
INDEX = 0


def _merged_diet_names():
    return set(
        DietComponentMerge.objects.filter(
            date=DATE, meal=MEAL, component_index=INDEX
        ).values_list("diet__name", flat=True)
    )


def test_merging_a_plain_diet_with_no_composites_just_works():
    diet = Diet.objects.create(name="Bez lepku")
    error = apply_diet_component_merge_toggle(DATE, MEAL, INDEX, diet, merged=True)
    assert error is None
    assert _merged_diet_names() == {"Bez lepku"}


def test_composite_cannot_be_merged_while_a_base_diet_is_still_separate():
    milk = Diet.objects.create(name="NoMilk")
    gluten = Diet.objects.create(name="NoGluten")
    combo = Diet.objects.create(name="NoMilk+NoGluten")
    combo.base_diets.set([milk, gluten])

    error = apply_diet_component_merge_toggle(DATE, MEAL, INDEX, combo, merged=True)

    assert error is not None
    assert "NoMilk" in error or "NoGluten" in error
    assert _merged_diet_names() == set()


def test_composite_can_be_merged_once_every_base_diet_is_merged():
    milk = Diet.objects.create(name="NoMilk")
    gluten = Diet.objects.create(name="NoGluten")
    combo = Diet.objects.create(name="NoMilk+NoGluten")
    combo.base_diets.set([milk, gluten])
    apply_diet_component_merge_toggle(DATE, MEAL, INDEX, milk, merged=True)
    apply_diet_component_merge_toggle(DATE, MEAL, INDEX, gluten, merged=True)

    error = apply_diet_component_merge_toggle(DATE, MEAL, INDEX, combo, merged=True)

    assert error is None
    assert _merged_diet_names() == {"NoMilk", "NoGluten", "NoMilk+NoGluten"}


def test_separating_a_base_diet_forces_its_composites_back_to_separate():
    milk = Diet.objects.create(name="NoMilk")
    gluten = Diet.objects.create(name="NoGluten")
    combo = Diet.objects.create(name="NoMilk+NoGluten")
    combo.base_diets.set([milk, gluten])
    apply_diet_component_merge_toggle(DATE, MEAL, INDEX, milk, merged=True)
    apply_diet_component_merge_toggle(DATE, MEAL, INDEX, gluten, merged=True)
    apply_diet_component_merge_toggle(DATE, MEAL, INDEX, combo, merged=True)
    assert _merged_diet_names() == {"NoMilk", "NoGluten", "NoMilk+NoGluten"}

    error = apply_diet_component_merge_toggle(DATE, MEAL, INDEX, milk, merged=False)

    assert error is None
    # NoMilk aj kombinácia (ktorá ju obsahuje) sú teraz obe zvlášť; NoGluten
    # sama o sebe zvlášťou byť nemusí, jej vlastný stav sa nemení.
    assert _merged_diet_names() == {"NoGluten"}


def test_cascade_only_touches_composites_actually_containing_the_base_diet():
    milk = Diet.objects.create(name="NoMilk")
    egg = Diet.objects.create(name="NoEgg")
    milk_gluten = Diet.objects.create(name="NoMilk+NoGluten")
    milk_gluten.base_diets.set([milk, Diet.objects.create(name="NoGluten")])
    egg_only_combo = Diet.objects.create(name="NoEgg+NoOrech")
    egg_only_combo.base_diets.set([egg, Diet.objects.create(name="NoOrech")])
    DietComponentMerge.objects.create(
        date=DATE, meal=MEAL, component_index=INDEX, diet=egg_only_combo
    )

    apply_diet_component_merge_toggle(DATE, MEAL, INDEX, milk, merged=False)

    # NoEgg+NoOrech nemá NoMilk ako zložku, zrušenie NoMilk sa ho netýka.
    assert "NoEgg+NoOrech" in _merged_diet_names()
    assert "NoMilk+NoGluten" not in _merged_diet_names()


def test_separating_a_component_that_was_never_merged_is_a_harmless_noop():
    diet = Diet.objects.create(name="Bez lepku")
    error = apply_diet_component_merge_toggle(DATE, MEAL, INDEX, diet, merged=False)
    assert error is None
    assert _merged_diet_names() == set()
