import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from api.management.commands import (
    assign_confirmed_edupage_dedup_diets_2026_09 as command_module,
)
from api.models import Celok, Diet, Prevadzka, PrevadzkaDiet

pytestmark = pytest.mark.django_db


@pytest.fixture
def assignment(monkeypatch):
    monkeypatch.setattr(
        command_module,
        "ASSIGNMENTS",
        (("Test celok", "Test prevádzka", "Nová kombinovaná diéta"),),
    )


def test_dry_run_does_not_add_visible_diet(assignment):
    celok = Celok.objects.create(nazov="Test celok")
    prevadzka = Prevadzka.objects.create(celok=celok, nazov="Test prevádzka")
    diet = Diet.objects.create(name="Nová kombinovaná diéta")

    call_command("assign_confirmed_edupage_dedup_diets_2026_09")

    assert not PrevadzkaDiet.objects.filter(prevadzka=prevadzka, diet=diet).exists()


def test_apply_adds_confirmed_visible_diet_idempotently(assignment):
    celok = Celok.objects.create(nazov="Test celok")
    prevadzka = Prevadzka.objects.create(celok=celok, nazov="Test prevádzka")
    diet = Diet.objects.create(name="Nová kombinovaná diéta")

    call_command("assign_confirmed_edupage_dedup_diets_2026_09", "--apply")
    call_command("assign_confirmed_edupage_dedup_diets_2026_09", "--apply")

    assert PrevadzkaDiet.objects.filter(prevadzka=prevadzka, diet=diet).count() == 1


def test_missing_target_aborts_before_any_assignment(assignment):
    celok = Celok.objects.create(nazov="Test celok")
    prevadzka = Prevadzka.objects.create(celok=celok, nazov="Test prevádzka")

    with pytest.raises(CommandError, match="chýba"):
        call_command("assign_confirmed_edupage_dedup_diets_2026_09", "--apply")

    assert not PrevadzkaDiet.objects.filter(prevadzka=prevadzka).exists()
