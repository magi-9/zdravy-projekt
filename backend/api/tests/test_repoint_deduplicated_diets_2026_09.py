import datetime

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from api.management.commands import repoint_deduplicated_diets_2026_09 as command_module
from api.models import (
    Celok,
    DailyMealPlan,
    Diet,
    DietComponentMerge,
    MealCategory,
    MealPlanItem,
    MealTemplate,
    Prevadzka,
    PrevadzkaDiet,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def mapping(monkeypatch):
    monkeypatch.setattr(command_module, "MAPPINGS", (("Stará", "Nová"),))


def _template(diet):
    return MealTemplate.objects.create(
        category=MealCategory.MAIN_COURSE,
        name="Test jedlo",
        base_weight_grams=100,
        diet=diet,
    )


def test_apply_repoints_every_live_diet_reference_and_keeps_legacy_diet(mapping):
    old = Diet.objects.create(name="Stará")
    new = Diet.objects.create(name="Nová")
    component = Diet.objects.create(name="Zložka")
    old.base_diets.add(component)

    celok = Celok.objects.create(nazov="Celok")
    prevadzka = Prevadzka.objects.create(celok=celok, nazov="Prevádzka")
    PrevadzkaDiet.objects.create(prevadzka=prevadzka, diet=old, note="dôležitá")

    template = _template(old)
    plan = DailyMealPlan.objects.create(date=datetime.date(2026, 9, 20))
    item = MealPlanItem.objects.create(
        meal_plan=plan,
        template=template,
        category=MealCategory.MAIN_COURSE,
        diet=old,
    )
    merge = DietComponentMerge.objects.create(
        date=datetime.date(2026, 9, 20),
        meal=MealCategory.MAIN_COURSE,
        component_index=0,
        diet=old,
    )

    call_command("repoint_deduplicated_diets_2026_09", "--apply")

    assert PrevadzkaDiet.objects.get(prevadzka=prevadzka, diet=new).note == "dôležitá"
    assert not PrevadzkaDiet.objects.filter(prevadzka=prevadzka, diet=old).exists()
    template.refresh_from_db()
    item.refresh_from_db()
    merge.refresh_from_db()
    assert template.diet == new
    assert item.diet == new
    assert merge.diet == new
    assert set(new.base_diets.values_list("pk", flat=True)) == {component.pk}
    assert Diet.objects.filter(pk=old.pk).exists()


def test_conflicting_existing_prevadzka_assignment_aborts_without_changes(mapping):
    old = Diet.objects.create(name="Stará")
    new = Diet.objects.create(name="Nová")
    celok = Celok.objects.create(nazov="Celok")
    prevadzka = Prevadzka.objects.create(celok=celok, nazov="Prevádzka")
    PrevadzkaDiet.objects.create(prevadzka=prevadzka, diet=old, note="stará poznámka")
    PrevadzkaDiet.objects.create(prevadzka=prevadzka, diet=new, note="nová poznámka")

    with pytest.raises(CommandError, match="konflikty"):
        call_command("repoint_deduplicated_diets_2026_09", "--apply")

    assert PrevadzkaDiet.objects.filter(prevadzka=prevadzka, diet=old).exists()
    assert PrevadzkaDiet.objects.filter(prevadzka=prevadzka, diet=new).exists()


def test_dry_run_never_writes(mapping):
    old = Diet.objects.create(name="Stará")
    new = Diet.objects.create(name="Nová")
    celok = Celok.objects.create(nazov="Celok")
    prevadzka = Prevadzka.objects.create(celok=celok, nazov="Prevádzka")
    PrevadzkaDiet.objects.create(prevadzka=prevadzka, diet=old)

    call_command("repoint_deduplicated_diets_2026_09", "--dry-run")

    assert PrevadzkaDiet.objects.filter(prevadzka=prevadzka, diet=old).exists()
    assert not PrevadzkaDiet.objects.filter(prevadzka=prevadzka, diet=new).exists()


def test_missing_target_aborts_without_writes(mapping):
    old = Diet.objects.create(name="Stará")
    celok = Celok.objects.create(nazov="Celok")
    prevadzka = Prevadzka.objects.create(celok=celok, nazov="Prevádzka")
    PrevadzkaDiet.objects.create(prevadzka=prevadzka, diet=old)

    with pytest.raises(CommandError, match="chýba"):
        call_command("repoint_deduplicated_diets_2026_09", "--apply")

    assert PrevadzkaDiet.objects.filter(prevadzka=prevadzka, diet=old).exists()


def test_old_diet_used_as_a_component_blocks_apply_instead_of_creating_nested_composite(
    mapping,
):
    old = Diet.objects.create(name="Stará")
    Diet.objects.create(name="Nová")
    composite = Diet.objects.create(name="Iná kombinácia")
    composite.base_diets.add(old)

    with pytest.raises(CommandError, match="vyžaduje manuálne posúdenie"):
        call_command("repoint_deduplicated_diets_2026_09", "--apply")

    assert composite.base_diets.filter(pk=old.pk).exists()
