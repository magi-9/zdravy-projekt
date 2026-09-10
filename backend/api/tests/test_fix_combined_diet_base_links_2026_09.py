import pytest
from django.core.management import call_command

from api.management.commands.fix_combined_diet_base_links_2026_09 import (
    DIET_1_COMPONENTS,
    DIET_1_NAME,
    DIET_2_COMPONENTS,
    DIET_2_LEGACY_NAME,
    DIET_2_NAME,
)
from api.models import Celok, Diet, Prevadzka, PrevadzkaDiet


@pytest.mark.django_db
def test_diet_1_already_exists_gets_base_diets_linked_without_losing_id():
    """Diéta #1 už v DB je (id sa nesmie zmeniť — inak by sa stratilo
    priradenie k prevádzke cez PrevadzkaDiet, id=128 zo živej DB, 10.9.2026)."""
    existing = Diet.objects.create(name=DIET_1_NAME)
    original_id = existing.id
    celok = Celok.objects.create(nazov="Test Celok")
    prevadzka = Prevadzka.objects.create(celok=celok, nazov="Test Prevadzka")
    PrevadzkaDiet.objects.create(prevadzka=prevadzka, diet=existing)

    call_command("fix_combined_diet_base_links_2026_09")

    existing.refresh_from_db()
    assert existing.id == original_id
    assert Diet.objects.filter(name=DIET_1_NAME).count() == 1
    assert sorted(existing.base_diets.values_list("name", flat=True)) == sorted(
        DIET_1_COMPONENTS
    )
    # Priradenie k prevádzke prežilo — rovnaké id, rovnaký PrevadzkaDiet riadok.
    assert PrevadzkaDiet.objects.filter(prevadzka=prevadzka, diet=existing).exists()


@pytest.mark.django_db
def test_diet_1_missing_components_get_matched_by_existing_name():
    for name in DIET_1_COMPONENTS:
        Diet.objects.create(name=name)
    Diet.objects.create(name=DIET_1_NAME)

    call_command("fix_combined_diet_base_links_2026_09")

    diet = Diet.objects.get(name=DIET_1_NAME)
    assert sorted(diet.base_diets.values_list("name", flat=True)) == sorted(
        DIET_1_COMPONENTS
    )
    # No duplicate single diets were created.
    for name in DIET_1_COMPONENTS:
        assert Diet.objects.filter(name=name).count() == 1


@pytest.mark.django_db
def test_diet_2_is_created_with_missing_single_diets():
    """Diéta #2 (163 znakov) predtým vôbec neexistovala — príkaz ju musí
    vytvoriť aj s dvoma chýbajúcimi jednozložkovými diétami (NO CITRUSY,
    NO SOSOVICA neboli v appke pod týmto presným menom)."""
    for name in DIET_2_COMPONENTS:
        if name not in ("NO CITRUSY", "NO SOSOVICA"):
            Diet.objects.create(name=name)

    call_command("fix_combined_diet_base_links_2026_09")

    diet = Diet.objects.get(name=DIET_2_NAME)
    assert len(diet.name) > 100  # presahuje starý (100) limit, dôkaz fixu #110
    assert sorted(diet.base_diets.values_list("name", flat=True)) == sorted(
        DIET_2_COMPONENTS
    )
    assert Diet.objects.filter(name="NO CITRUSY").exists()
    assert Diet.objects.filter(name="NO SOSOVICA").exists()


@pytest.mark.django_db
def test_diet_2_links_to_existing_legacy_named_diet_instead_of_duplicating():
    """Prod (10.9.2026): rovnaká kombinácia už existuje pod starým menom
    (`id=46`, "NONONO..."), aktívne priradená prevádzke a používaná v
    objednávkach. Príkaz na ňu MUSÍ naviazať base_diets namiesto založenia
    duplicitnej novej diéty pod `DIET_2_NAME` — inak by problém ostal
    nevyriešený a pribudla by len nepoužívaná diéta naviac."""
    for name in DIET_2_COMPONENTS:
        if name not in ("NO CITRUSY", "NO SOSOVICA"):
            Diet.objects.create(name=name)
    legacy = Diet.objects.create(name=DIET_2_LEGACY_NAME)
    legacy_id = legacy.id
    celok = Celok.objects.create(nazov="Little Big")
    prevadzka = Prevadzka.objects.create(celok=celok, nazov="Little Big")
    PrevadzkaDiet.objects.create(prevadzka=prevadzka, diet=legacy)

    call_command("fix_combined_diet_base_links_2026_09")

    # No new diet created under the new dash-joined name.
    assert not Diet.objects.filter(name=DIET_2_NAME).exists()
    legacy.refresh_from_db()
    assert legacy.id == legacy_id
    assert legacy.name == DIET_2_LEGACY_NAME
    assert sorted(legacy.base_diets.values_list("name", flat=True)) == sorted(
        DIET_2_COMPONENTS
    )
    # Priradenie k prevádzke prežilo.
    assert PrevadzkaDiet.objects.filter(prevadzka=prevadzka, diet=legacy).exists()


@pytest.mark.django_db
def test_command_is_idempotent():
    for name in DIET_1_COMPONENTS + DIET_2_COMPONENTS:
        Diet.objects.get_or_create(name=name)

    call_command("fix_combined_diet_base_links_2026_09")
    first = sorted(Diet.objects.values_list("name", flat=True))

    call_command("fix_combined_diet_base_links_2026_09")
    second = sorted(Diet.objects.values_list("name", flat=True))

    assert first == second
    assert Diet.objects.filter(name=DIET_1_NAME).count() == 1
    assert Diet.objects.filter(name=DIET_2_NAME).count() == 1


@pytest.mark.django_db
def test_dry_run_makes_no_changes():
    before = list(Diet.objects.values_list("name", flat=True))

    call_command("fix_combined_diet_base_links_2026_09", "--dry-run")

    after = list(Diet.objects.values_list("name", flat=True))
    assert before == after
