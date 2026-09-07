from contextlib import nullcontext
from unittest.mock import Mock, call

import pytest
from django.contrib.auth.models import User
from django.core import management
from django_celery_beat.models import PeriodicTask

from api.default_visibility import DEFAULT_VISIBLE_MENUS
from api.management.commands import deploy_bootstrap, seed_operations
from api.management.commands.real_initial_seed_prevadzky import (
    EDUPAGE_VISIBLE_MEALS,
    SCHOOLS,
)
from api.management.commands.seed_real_delivery_layout import DELIVERY_ROWS, ROUTES
from api.models import (
    Celok,
    DeliveryBlock,
    DeliveryRoute,
    Diet,
    EventLog,
    GlobalSettings,
    Prevadzka,
    UserProfile,
)
from api.reference_data import DEFAULT_DIET_NAMES
from api.signals import EDUPAGE_SCRAPE_TASK_PREFIX


def test_deploy_bootstrap_calls_only_static_commands_in_order(monkeypatch):
    call_command = Mock()
    bootstrap_lock = Mock(return_value=nullcontext())
    monkeypatch.setattr(deploy_bootstrap.management, "call_command", call_command)
    monkeypatch.setattr(deploy_bootstrap, "deploy_bootstrap_lock", bootstrap_lock)

    deploy_bootstrap.Command().handle(skip_migrate=False, verbosity=2)

    bootstrap_lock.assert_called_once_with()
    assert call_command.call_args_list == [
        call("migrate", verbosity=2),
        call("init_roles", verbosity=2),
        call("init_reference_data", verbosity=2),
        call("ensure_global_settings", verbosity=2),
        call("sync_periodic_tasks", "--fix", verbosity=2),
    ]


def test_seed_operations_calls_data_seeds_in_order(monkeypatch):
    call_command = Mock()
    bootstrap_lock = Mock(return_value=nullcontext())
    assert (
        seed_operations.deploy_bootstrap_lock is deploy_bootstrap.deploy_bootstrap_lock
    )
    monkeypatch.setattr(seed_operations.management, "call_command", call_command)
    monkeypatch.setattr(seed_operations, "deploy_bootstrap_lock", bootstrap_lock)

    seed_operations.Command().handle(verbosity=2)

    bootstrap_lock.assert_called_once_with()
    assert call_command.call_args_list == [
        call("real_initial_seed_prevadzky", "--allow-prod", verbosity=2),
        call("seed_prevadzky_edupage", verbosity=2),
        call("seed_zdrave_brusko", verbosity=2),
        call("seed_real_delivery_layout", "--allow-prod", verbosity=2),
        call("seed_merge_celky", verbosity=2),
        call("seed_bystra_breakfast_from_lunch", verbosity=2),
        call("seed_new_edupage_2026_08", verbosity=2),
        call("seed_british_school_2026_08", verbosity=2),
        call("seed_cms_pezinok_2026_08", verbosity=2),
        call("seed_skolicka_zs_2026_09", verbosity=2),
        call("seed_rozmanita_split_2026_09", verbosity=2),
        call("seed_nasa_skola_poznania_split_2026_09", verbosity=2),
    ]


@pytest.mark.django_db
def test_ensure_global_settings_creates_singleton_idempotently():
    assert not GlobalSettings.objects.filter(pk=1).exists()

    management.call_command("ensure_global_settings")
    management.call_command("ensure_global_settings")

    assert GlobalSettings.objects.filter(pk=1).count() == 1


@pytest.mark.django_db
def test_real_edupage_seed_creates_operations_and_links(settings):
    settings.DEBUG = False

    management.call_command("init_reference_data")
    management.call_command("real_initial_seed_prevadzky", "--allow-prod")
    management.call_command("real_initial_seed_prevadzky", "--allow-prod")

    assert User.objects.filter(username__endswith="@edupage.local").count() == len(
        SCHOOLS
    )

    for school in SCHOOLS:
        user = User.objects.get(username=f"{school['subdomain']}@edupage.local")
        profile = user.profile

        assert not user.has_usable_password()
        assert profile.company_name == school["company_name"]
        assert profile.is_edupage_only()

    dia = Diet.objects.get(name="DIA")
    krasnanko = User.objects.get(username="krasnanko@edupage.local")
    assert (
        krasnanko.profile.dostupne_prevadzky()
        .get()
        .visible_diets.filter(pk=dia.pk)
        .exists()
    )
    for school in SCHOOLS:
        prevadzky = User.objects.get(
            username=f"{school['subdomain']}@edupage.local"
        ).profile.dostupne_prevadzky()
        assert prevadzky.exists()
        for prevadzka in prevadzky:
            assert prevadzka.visible_menus == DEFAULT_VISIBLE_MENUS
            assert prevadzka.visible_meals == EDUPAGE_VISIBLE_MEALS
            enabled_diets = set(prevadzka.visible_diets.values_list("name", flat=True))
            assert set(DEFAULT_DIET_NAMES).issubset(enabled_diets)
            if school["subdomain"] != "krasnanko":
                assert "DIA" not in enabled_diets
            assert prevadzka.celok.billing_name == school["company_name"]
            assert prevadzka.celok.zdroj_objednavok == Celok.ZdrojObjednavok.EDUPAGE
            assert prevadzka.edupage_connection is not None
            assert (
                prevadzka.edupage_connection.mealsguest_url == school["mealsguest_url"]
            )


@pytest.mark.django_db
def test_real_delivery_layout_seed_is_idempotent_and_persistent(settings):
    settings.DEBUG = True
    Diet.objects.create(name="NO GLUTEN")
    old_zdrave_brusko_celok = Celok.objects.create(nazov="MŠ Zdravé Bruško")
    old_zdrave_brusko = Prevadzka.objects.create(
        celok=old_zdrave_brusko_celok,
        nazov="MŠ Zdravé Bruško",
    )
    ivanka_celok = Celok.objects.create(nazov="ZŠ Ivanka pri Dunaji")
    ivanka = Prevadzka.objects.create(celok=ivanka_celok, nazov="ZŠ Ivanka pri Dunaji")
    veterinarna_celok = Celok.objects.create(nazov="SŠ VETERINÁRNA")
    veterinarna = Prevadzka.objects.create(
        celok=veterinarna_celok,
        nazov="SŠ VETERINÁRNA",
        adresa="Pod brehmi 6, Bratislava",
    )
    fan_celok = Celok.objects.create(nazov="SZŠ FAN")
    fan = Prevadzka.objects.create(celok=fan_celok, nazov="SZŠ FAN")

    management.call_command("seed_real_delivery_layout")
    management.call_command("seed_real_delivery_layout")

    assert (
        DeliveryBlock.objects.filter(name__in=["Bežné trasy", "Trasa extra"]).count()
        == 2
    )
    assert DeliveryRoute.objects.count() == len(ROUTES)
    assert Prevadzka.objects.filter(is_active=True).count() == len(DELIVERY_ROWS)

    nova_tulipa = Prevadzka.objects.get(nazov="Nova Tulipa")
    assert nova_tulipa.delivery_route.name == "trasa 2 - 9:25 - Ivan/Heňo"
    assert nova_tulipa.delivery_sort_order == 1

    ivanka.refresh_from_db()
    assert ivanka.delivery_route.name == "1.Trasa - Pezinská - Heňo/Ivan"
    assert ivanka.delivery_sort_order == 5
    assert ivanka.report_alias == "Ivanka"

    veterinarna.refresh_from_db()
    assert (
        veterinarna.delivery_route.name == "TRASA EXTRA ZABALENÉ ZVLÁŠŤ - do 11:00 MAJO"
    )
    assert veterinarna.report_alias == "SŠ VETERINÁRNA Pod brehmi 6"

    fan.refresh_from_db()
    assert fan.delivery_route.name == "trasa 5 - RADKO - 10:00"
    assert fan.report_alias == "Fantastická škola"

    for name in [
        "Hravou Formou bez raňajok",
        "Korálky",
        "Koliba",
        "Little Big",
        "Veselý Úľ 1",
        "Veselý Úľ 2",
        "Simon Drgo MŠ Milana Marečka 20, DNV",
        "Malokarpatské námestie 2, Lamač",
        "Hodonínska 27",
        "Športová 450, Šamorín",
        "Steinov dvor 2, Bratislava",
        "Pozri dokument kvôli dennej adrese",
    ]:
        assert Prevadzka.objects.filter(nazov=name, is_active=True).exists()

    assert not Celok.objects.filter(pk=old_zdrave_brusko_celok.pk).exists()
    assert not Prevadzka.objects.filter(pk=old_zdrave_brusko.pk).exists()

    for nazov in ["Jolly 1", "Jolly 2", "Jolly 3", "Les", "Lúka"]:
        assert (
            Prevadzka.objects.get(nazov=nazov).celok.zdroj_objednavok
            == Celok.ZdrojObjednavok.EDUPAGE
        )

    no_gluten = Diet.objects.get(name="NO GLUTEN")
    assert no_gluten.color == "#2563EB"


@pytest.mark.django_db
def test_missing_multi_rows_merge_under_one_celok_idempotently(settings):
    settings.DEBUG = True
    management.call_command("seed_real_delivery_layout")
    management.call_command("seed_merge_celky")
    management.call_command("seed_real_delivery_layout")
    management.call_command("seed_merge_celky")

    expected = {
        "ZŠ Malokarpatská": {"ZŠ Malokarpatská", "Malokarpatské námestie 2, Lamač"},
        "Zvlášť!!! Tábor Warrior": {"Zvlášť!!! Tábor Warrior", "Hodonínska 27"},
        "Zvlášť!!! Futbalový Tábor": {
            "Zvlášť!!! Futbalový Tábor",
            "Športová 450, Šamorín",
        },
        "Zvlášť!!! Tábor Paint People": {
            "Zvlášť!!! Tábor Paint People",
            "Steinov dvor 2, Bratislava",
        },
        "Zvlášť!!! Vojenský Tábor": {
            "Zvlášť!!! Vojenský Tábor",
            "Pozri dokument kvôli dennej adrese",
        },
    }
    for celok_name, prevadzky in expected.items():
        celok = Celok.objects.get(nazov=celok_name)
        assert set(celok.prevadzky.values_list("nazov", flat=True)) == prevadzky


@pytest.mark.django_db
def test_real_edupage_seed_fills_blank_billing_name(settings):
    settings.DEBUG = False
    school = SCHOOLS[0]
    user = User.objects.create_user(
        username=f"{school['subdomain']}@edupage.local",
        email=f"{school['subdomain']}@edupage.local",
    )
    UserProfile.objects.create(user=user)

    management.call_command("real_initial_seed_prevadzky", "--allow-prod")

    user.refresh_from_db()
    assert user.profile.company_name == school["company_name"]
    celok = user.profile.primary_celok()
    prevadzka = user.profile.dostupne_prevadzky().get()
    assert celok.nazov == school["company_name"]
    assert celok.billing_name == school["company_name"]
    assert celok.zdroj_objednavok == Celok.ZdrojObjednavok.EDUPAGE
    assert prevadzka.edupage_connection.mealsguest_url == school["mealsguest_url"]


@pytest.mark.django_db
def test_real_edupage_seed_does_not_reset_admin_narrowed_visible_menus(settings):
    """Regression test: an admin's narrowed visible_menus/visible_meals must
    survive a re-run of real_initial_seed_prevadzky (which runs on every dev
    startup and is part of the same idempotent chain as init_reference_data
    in prod). Previously this silently reset any admin customization back to
    "everything enabled" on each run."""
    settings.DEBUG = False
    school = SCHOOLS[0]
    user = User.objects.create_user(
        username=f"{school['subdomain']}@edupage.local",
        email=f"{school['subdomain']}@edupage.local",
    )
    UserProfile.objects.create(user=user)
    prevadzka = user.profile.dostupne_prevadzky().get()
    prevadzka.visible_menus = ["A"]
    prevadzka.visible_meals = ["lunch"]
    prevadzka.save(update_fields=["visible_menus", "visible_meals"])

    management.call_command("real_initial_seed_prevadzky", "--allow-prod")

    prevadzka.refresh_from_db()
    assert prevadzka.visible_menus == ["A"]
    assert prevadzka.visible_meals == ["lunch"]


@pytest.mark.django_db
def test_real_edupage_seed_does_not_attach_rozmanita_school_after_merge(settings):
    settings.DEBUG = False

    management.call_command("init_reference_data")
    management.call_command("real_initial_seed_prevadzky", "--allow-prod")
    management.call_command("seed_real_delivery_layout")
    management.call_command("seed_merge_celky")
    management.call_command("real_initial_seed_prevadzky", "--allow-prod")

    skolicka = Prevadzka.objects.get(nazov="MŠ Rozmanitá")
    skola = Prevadzka.objects.get(nazov="Rozmanita Škola")

    assert skolicka.celok == skola.celok
    assert skolicka.edupage_connection is not None
    assert "rozmanita.edupage.org" in skolicka.edupage_connection.mealsguest_url
    assert skola.edupage_connection is None


@pytest.mark.django_db
def test_deploy_bootstrap_creates_edupage_scrape_tasks(settings):
    settings.DEBUG = False

    management.call_command("deploy_bootstrap", "--skip-migrate")

    assert PeriodicTask.objects.filter(
        name__startswith=EDUPAGE_SCRAPE_TASK_PREFIX,
        enabled=True,
        task="api.tasks.scrape_edupage_orders_task",
    ).exists()


@pytest.mark.django_db
def test_disabled_edupage_auto_scrape_removes_periodic_tasks(settings):
    settings.DEBUG = False

    gs = GlobalSettings.objects.create(pk=1, edupage_auto_scrape_enabled=True)
    assert PeriodicTask.objects.filter(
        name__startswith=EDUPAGE_SCRAPE_TASK_PREFIX
    ).exists()

    gs.edupage_auto_scrape_enabled = False
    gs.save(update_fields=["edupage_auto_scrape_enabled"])

    assert not PeriodicTask.objects.filter(
        name__startswith=EDUPAGE_SCRAPE_TASK_PREFIX
    ).exists()


@pytest.mark.django_db
def test_deploy_bootstrap_does_not_create_demo_logins_in_production(
    settings, monkeypatch
):
    settings.DEBUG = False
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "app.settings.prod")

    management.call_command("deploy_bootstrap", "--skip-migrate")

    assert not User.objects.filter(
        email__in=["admin@example.com", "prevadzka@example.com"]
    ).exists()


@pytest.mark.django_db
def test_deploy_bootstrap_logs_new_version_on_success(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "prod-abc123")

    management.call_command("deploy_bootstrap", "--skip-migrate")

    logs = EventLog.objects.filter(event_type=EventLog.EventType.DEPLOY_VERSION)
    assert logs.count() == 1
    assert logs.get().payload["version"] == "prod-abc123"


@pytest.mark.django_db
def test_deploy_bootstrap_does_not_log_again_for_the_same_version(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "prod-abc123")

    management.call_command("deploy_bootstrap", "--skip-migrate")
    management.call_command("deploy_bootstrap", "--skip-migrate")

    assert (
        EventLog.objects.filter(event_type=EventLog.EventType.DEPLOY_VERSION).count()
        == 1
    )


@pytest.mark.django_db
def test_deploy_bootstrap_logs_again_when_version_changes(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "prod-abc123")
    management.call_command("deploy_bootstrap", "--skip-migrate")

    monkeypatch.setenv("APP_VERSION", "prod-def456")
    management.call_command("deploy_bootstrap", "--skip-migrate")

    logs = EventLog.objects.filter(
        event_type=EventLog.EventType.DEPLOY_VERSION
    ).order_by("created_at")
    assert [log.payload["version"] for log in logs] == ["prod-abc123", "prod-def456"]


@pytest.mark.django_db
def test_deploy_bootstrap_does_not_log_version_without_env_var(monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)

    management.call_command("deploy_bootstrap", "--skip-migrate")

    assert not EventLog.objects.filter(
        event_type=EventLog.EventType.DEPLOY_VERSION
    ).exists()


@pytest.mark.django_db
def test_deploy_bootstrap_does_not_log_version_when_a_step_fails(monkeypatch):
    """Call handle() directly (like
    test_deploy_bootstrap_calls_only_static_commands_in_order) — going through
    management.call_command("deploy_bootstrap", ...) would itself be
    intercepted by the mocked call_command below, since deploy_bootstrap.py's
    `management` import is the same shared django.core.management module."""
    monkeypatch.setenv("APP_VERSION", "prod-abc123")

    monkeypatch.setattr(
        deploy_bootstrap.management,
        "call_command",
        Mock(
            side_effect=[None, None, None, RuntimeError("sync_periodic_tasks blew up")]
        ),
    )

    with pytest.raises(RuntimeError):
        deploy_bootstrap.Command().handle(skip_migrate=True, verbosity=1)

    assert not EventLog.objects.filter(
        event_type=EventLog.EventType.DEPLOY_VERSION
    ).exists()
