import pytest
from django.contrib.auth.models import Group, User
from django.core import management

from api.models import Celok, Prevadzka


@pytest.mark.django_db
def test_init_roles_skips_default_users_in_production(monkeypatch):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "app.settings.prod")

    management.call_command("init_roles")

    assert Group.objects.filter(name__in=["Client", "Admin", "Staff"]).count() == 3
    assert not User.objects.filter(
        email__in=["admin@example.com", "prevadzka@example.com"]
    ).exists()


@pytest.mark.django_db
def test_init_roles_creates_default_users_in_staging(monkeypatch):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "app.settings.staging")

    management.call_command("init_roles")

    admin_user = User.objects.get(email="admin@example.com")
    operation_user = User.objects.get(email="prevadzka@example.com")

    assert Group.objects.filter(name__in=["Client", "Admin", "Staff"]).count() == 3
    assert admin_user.username == "admin@example.com"
    assert admin_user.is_superuser is True
    assert admin_user.check_password("admin")
    assert operation_user.username == "prevadzka@example.com"
    assert operation_user.check_password("prevadzka")


@pytest.mark.django_db
def test_init_roles_creates_default_users_outside_production(monkeypatch):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "app.settings.dev")

    management.call_command("init_roles")

    assert User.objects.filter(
        username="admin@example.com",
        email="admin@example.com",
        is_superuser=True,
    ).exists()
    assert User.objects.filter(
        username="prevadzka@example.com",
        email="prevadzka@example.com",
    ).exists()


@pytest.mark.django_db
def test_init_roles_migrates_legacy_demo_logins(monkeypatch):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "app.settings.dev")
    User.objects.create_user(username="admin", email="admin", password="old")
    User.objects.create_user(username="prevadzka", email="prevadzka", password="old")

    management.call_command("init_roles")

    admin_user = User.objects.get(email="admin@example.com")
    operation_user = User.objects.get(email="prevadzka@example.com")

    assert admin_user.username == "admin@example.com"
    assert admin_user.check_password("admin")
    assert operation_user.username == "prevadzka@example.com"
    assert operation_user.check_password("prevadzka")


@pytest.mark.django_db
def test_fast_access_only_creates_no_demo_facilities(monkeypatch):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "app.settings.dev")
    celok = Celok.objects.create(nazov="Importovaná škola")
    prevadzka = Prevadzka.objects.create(celok=celok, nazov="Importovaná prevádzka")

    management.call_command("init_roles", "--fast-access-only")

    operation_user = User.objects.get(email="prevadzka@example.com")
    assert Celok.objects.count() == 1
    assert Prevadzka.objects.count() == 1
    assert set(operation_user.profile.dostupne_prevadzky()) == {prevadzka}
