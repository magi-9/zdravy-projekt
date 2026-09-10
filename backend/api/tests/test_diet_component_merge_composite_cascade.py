"""Kaskáda "spolu/zvlášť" pre kombinované diéty (#568 nadväzba, flip
10.9.2026).

Admin default vidí všetko "spolu" a odklikáva výnimky "zvlášť". Kombinovaná
diéta (`Diet.base_diets`) sa podľa základných diét riadi:
- aspoň jedna základná zložka "zvlášť" → kombinácia je automaticky "zvlášť"
  tiež (aj keby predtým bola explicitne "spolu" — kaskáda ju prepne),
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


def _separated_diet_names():
    return set(
        DietComponentMerge.objects.filter(
            date=DATE, meal=MEAL, component_index=INDEX
        ).values_list("diet__name", flat=True)
    )


def test_separating_a_plain_diet_with_no_composites_just_works():
    diet = Diet.objects.create(name="Bez lepku")
    error = apply_diet_component_merge_toggle(DATE, MEAL, INDEX, diet, merged=False)
    assert error is None
    assert _separated_diet_names() == {"Bez lepku"}


def test_composite_cannot_go_back_to_spolu_while_a_base_diet_is_still_separate():
    milk = Diet.objects.create(name="NoMilk")
    gluten = Diet.objects.create(name="NoGluten")
    combo = Diet.objects.create(name="NoMilk+NoGluten")
    combo.base_diets.set([milk, gluten])
    apply_diet_component_merge_toggle(DATE, MEAL, INDEX, milk, merged=False)

    error = apply_diet_component_merge_toggle(DATE, MEAL, INDEX, combo, merged=True)

    assert error is not None
    assert "NoMilk" in error
    # combo bolo kaskádou z milk automaticky "zvlášť" — klik na "spolu" sa
    # zamietol, zvlášť-riadok kombinácie ostáva.
    assert "NoMilk+NoGluten" in _separated_diet_names()


def test_composite_can_go_back_to_spolu_once_every_base_diet_is_spolu():
    milk = Diet.objects.create(name="NoMilk")
    gluten = Diet.objects.create(name="NoGluten")
    combo = Diet.objects.create(name="NoMilk+NoGluten")
    combo.base_diets.set([milk, gluten])
    apply_diet_component_merge_toggle(DATE, MEAL, INDEX, milk, merged=False)
    apply_diet_component_merge_toggle(DATE, MEAL, INDEX, gluten, merged=False)
    assert "NoMilk+NoGluten" in _separated_diet_names()

    apply_diet_component_merge_toggle(DATE, MEAL, INDEX, milk, merged=True)
    apply_diet_component_merge_toggle(DATE, MEAL, INDEX, gluten, merged=True)
    error = apply_diet_component_merge_toggle(DATE, MEAL, INDEX, combo, merged=True)

    assert error is None
    assert _separated_diet_names() == set()


def test_separating_a_base_diet_forces_its_composites_to_separate_too():
    milk = Diet.objects.create(name="NoMilk")
    gluten = Diet.objects.create(name="NoGluten")
    combo = Diet.objects.create(name="NoMilk+NoGluten")
    combo.base_diets.set([milk, gluten])

    error = apply_diet_component_merge_toggle(DATE, MEAL, INDEX, milk, merged=False)

    assert error is None
    # NoMilk aj kombinácia (ktorá ju obsahuje) sú teraz obe zvlášť; NoGluten
    # sama o sebe zvlášť byť nemusí, jej vlastný stav sa nemení.
    assert _separated_diet_names() == {"NoMilk", "NoMilk+NoGluten"}


def test_cascade_only_touches_composites_actually_containing_the_base_diet():
    milk = Diet.objects.create(name="NoMilk")
    egg = Diet.objects.create(name="NoEgg")
    milk_gluten = Diet.objects.create(name="NoMilk+NoGluten")
    milk_gluten.base_diets.set([milk, Diet.objects.create(name="NoGluten")])
    egg_only_combo = Diet.objects.create(name="NoEgg+NoOrech")
    egg_only_combo.base_diets.set([egg, Diet.objects.create(name="NoOrech")])
    # NoEgg+NoOrech je default "spolu" (žiadny zvlášť-riadok) — nemá NoMilk
    # ako zložku, takže zvlášť na NoMilk sa ho netýka.

    apply_diet_component_merge_toggle(DATE, MEAL, INDEX, milk, merged=False)

    assert "NoEgg+NoOrech" not in _separated_diet_names()
    assert "NoMilk+NoGluten" in _separated_diet_names()


def test_merging_back_a_component_that_was_never_separated_is_a_harmless_noop():
    diet = Diet.objects.create(name="Bez lepku")
    error = apply_diet_component_merge_toggle(DATE, MEAL, INDEX, diet, merged=True)
    assert error is None
    assert _separated_diet_names() == set()
