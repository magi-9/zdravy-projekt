"""`_split_diet_component_grams` (#568) — čistá funkcia, ktorá z gramáže
diétneho riadku vyberie zložky označené ako "spolu" a pripraví ich na
presun do štandardného riadku. Diétny riadok si ponecháva len "zvlášť"
zložky, presunuté zložky v ňom ostávajú prázdne ("—").
"""

from decimal import Decimal

from api.services.meal_plan_service import _split_diet_component_grams

# Tri stĺpcové skupiny (polievka, Menu A, Menu B) — diétny riadok má dáta
# len v jednej z nich (presne ako `_col_grams_diet` vracia).
EMPTY3 = [[], [], []]


def _diet_grams(group_index: int, values: list) -> list:
    grams = [list(g) for g in EMPTY3]
    grams[group_index] = values
    return grams


def test_no_merged_components_leaves_grams_untouched():
    grams = _diet_grams(1, ["100.00", "50.00"])
    new_grams, group_index, moved = _split_diet_component_grams(grams, set())
    assert new_grams == grams
    assert group_index is None
    assert moved == {}


def test_merging_one_component_zeroes_it_in_the_diet_row():
    grams = _diet_grams(1, ["100.00", "50.00"])
    new_grams, group_index, moved = _split_diet_component_grams(grams, {0})
    assert group_index == 1
    assert new_grams[1] == ["0.00", "50.00"]
    assert moved == {0: Decimal("100.00")}
    # Ostatné skupiny (polievka, Menu B) nedotknuté.
    assert new_grams[0] == []
    assert new_grams[2] == []


def test_merging_all_components_empties_the_diet_row():
    grams = _diet_grams(1, ["100.00", "50.00"])
    new_grams, group_index, moved = _split_diet_component_grams(grams, {0, 1})
    assert new_grams[1] == ["0.00", "0.00"]
    assert moved == {0: Decimal("100.00"), 1: Decimal("50.00")}


def test_merged_index_out_of_range_is_ignored():
    grams = _diet_grams(1, ["100.00"])
    new_grams, group_index, moved = _split_diet_component_grams(grams, {5})
    assert new_grams == grams
    assert group_index is None
    assert moved == {}


def test_merged_index_pointing_at_an_already_empty_cell_is_ignored():
    """Zložka bola vynulovaná (0/None) inou logikou skôr — nič na presun."""
    grams = _diet_grams(1, ["0.00", "50.00"])
    new_grams, group_index, moved = _split_diet_component_grams(grams, {0, 1})
    assert new_grams[1] == ["0.00", "0.00"]
    assert moved == {1: Decimal("50.00")}


def test_diet_row_with_no_populated_group_is_a_noop():
    """Diéta bez gramáže v tomto jedle (napr. iný meal) — nič na presun."""
    new_grams, group_index, moved = _split_diet_component_grams(EMPTY3, {0})
    assert new_grams == EMPTY3
    assert group_index is None
    assert moved == {}


def test_original_list_is_not_mutated():
    original = _diet_grams(1, ["100.00", "50.00"])
    snapshot = [list(g) for g in original]
    _split_diet_component_grams(original, {0})
    assert original == snapshot
