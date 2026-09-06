from io import StringIO

import pytest
from django.core.management import call_command

from api.management.commands.seed_british_school_2026_08 import (
    BRITISH_SCHOOL_DIET_NAMES,
    BRITISH_SCHOOL_URL,
)
from api.models import (
    Celok,
    DeliveryBlock,
    DeliveryRoute,
    Diet,
    EdupageConnection,
    Prevadzka,
    Vydaj,
)


def _seed_trasa_extra_block() -> DeliveryBlock:
    return DeliveryBlock.objects.create(
        name="Trasa extra", sort_order=2, include_in_extra_summary=True
    )


def _seed_british_school_diets() -> None:
    for name in BRITISH_SCHOOL_DIET_NAMES:
        Diet.objects.create(name=name)


@pytest.mark.django_db
def test_seed_british_school_creates_celok_prevadzka_and_edupage_link():
    call_command("seed_british_school_2026_08")

    celok = Celok.objects.get(nazov="British School")
    prevadzka = celok.prevadzky.get(nazov="British School")
    assert celok.zdroj_objednavok == Celok.ZdrojObjednavok.EDUPAGE
    assert prevadzka.edupage_connection.mealsguest_url == BRITISH_SCHOOL_URL
    assert prevadzka.edupage_match == ""
    assert (
        EdupageConnection.objects.filter(mealsguest_url=BRITISH_SCHOOL_URL).count() == 1
    )


@pytest.mark.django_db
def test_seed_british_school_sets_its_dedicated_scrape_time():
    """Code review follow-up (2026-08-31): British School's scrape crontab
    generalized off a hardcoded connection name onto
    EdupageConnection.dedicated_scrape_hour/minute - the seed must still set
    it, or the connection silently falls back to the shared deadlines."""
    call_command("seed_british_school_2026_08")

    connection = EdupageConnection.objects.get(mealsguest_url=BRITISH_SCHOOL_URL)
    assert connection.dedicated_scrape_hour == 12
    assert connection.dedicated_scrape_minute == 15


@pytest.mark.django_db
def test_seed_british_school_repairs_a_cleared_dedicated_scrape_time():
    """Re-running the (idempotent) seed must restore the dedicated schedule
    even if it was cleared on the existing row in the meantime."""
    call_command("seed_british_school_2026_08")
    connection = EdupageConnection.objects.get(mealsguest_url=BRITISH_SCHOOL_URL)
    connection.dedicated_scrape_hour = None
    connection.dedicated_scrape_minute = None
    connection.save(update_fields=["dedicated_scrape_hour", "dedicated_scrape_minute"])

    call_command("seed_british_school_2026_08")

    connection.refresh_from_db()
    assert connection.dedicated_scrape_hour == 12
    assert connection.dedicated_scrape_minute == 15


@pytest.mark.django_db
def test_seed_british_school_enables_its_translated_diets_when_they_exist():
    _seed_british_school_diets()

    call_command("seed_british_school_2026_08")

    prevadzka = Prevadzka.objects.get(nazov="British School")
    enabled = set(prevadzka.visible_diets.values_list("name", flat=True))
    assert enabled == set(BRITISH_SCHOOL_DIET_NAMES)


@pytest.mark.django_db
def test_seed_british_school_warns_when_its_diets_are_missing():
    stdout = StringIO()

    call_command("seed_british_school_2026_08", stdout=stdout)

    assert "diéty" in stdout.getvalue() and "chýbajú" in stdout.getvalue()
    prevadzka = Prevadzka.objects.get(nazov="British School")
    assert prevadzka.visible_diets.count() == 0


@pytest.mark.django_db
def test_seed_british_school_assigns_a_cluster_c_route_when_trasa_extra_exists():
    _seed_trasa_extra_block()

    call_command("seed_british_school_2026_08")

    prevadzka = Prevadzka.objects.get(nazov="British School")
    route = prevadzka.delivery_route
    assert route is not None
    assert route.vydaj == Vydaj.C
    assert route.block.name == "Trasa extra"


@pytest.mark.django_db
def test_seed_british_school_warns_when_trasa_extra_is_missing():
    stdout = StringIO()

    call_command("seed_british_school_2026_08", stdout=stdout)

    assert "blok 'Trasa extra' neexistuje" in stdout.getvalue()
    prevadzka = Prevadzka.objects.get(nazov="British School")
    assert prevadzka.delivery_route is None


@pytest.mark.django_db
def test_seed_british_school_enables_menu_d_and_vege1():
    """Menu D a VEGE1 (4. obedové menu, Cluster C sumár) sú British School
    špecifiká, neviditeľné pre žiadnu inú prevádzku (`DEFAULT_VISIBLE_MENUS` ich
    neobsahuje, migrácia 0097 ich zo všetkých ostatných odstránila) — seed ich
    musí British explicitne zapnúť (user 4.9.2026: "má byť disabled teda
    neviditeľná inak pre british úplne rovnako ako menu Vege 1")."""
    call_command("seed_british_school_2026_08")

    prevadzka = Prevadzka.objects.get(nazov="British School")
    assert "D" in prevadzka.visible_menus
    assert "VEGE1" in prevadzka.visible_menus


@pytest.mark.django_db
def test_seed_british_school_repairs_menu_d_and_vege1_if_removed():
    """Re-run musí obnoviť D/VEGE1 aj keby ich niekto medzičasom odstránil
    (rovnaký idempotentný repair vzor ako dedicated_scrape_hour vyššie)."""
    call_command("seed_british_school_2026_08")
    prevadzka = Prevadzka.objects.get(nazov="British School")
    prevadzka.visible_menus = ["A", "B", "C", "V"]
    prevadzka.save(update_fields=["visible_menus"])

    call_command("seed_british_school_2026_08")

    prevadzka.refresh_from_db()
    assert "D" in prevadzka.visible_menus
    assert "VEGE1" in prevadzka.visible_menus


@pytest.mark.django_db
def test_seed_british_school_marks_gramage_summary_only():
    """British nemá gramážové menu-šablóny — gramážna tabuľka/PDF ju musí
    vykazovať len ako kusový Cluster C sumár, nie cez bežnú mriežku (#531)."""
    call_command("seed_british_school_2026_08")

    prevadzka = Prevadzka.objects.get(nazov="British School")
    assert prevadzka.gramage_summary_only is True


@pytest.mark.django_db
def test_seed_british_school_is_idempotent():
    _seed_trasa_extra_block()
    call_command("seed_british_school_2026_08")
    first_state = {
        "celky": list(Celok.objects.order_by("pk").values()),
        "prevadzky": list(Prevadzka.objects.order_by("pk").values()),
        "connections": list(EdupageConnection.objects.order_by("pk").values()),
        "routes": list(DeliveryRoute.objects.order_by("pk").values()),
    }

    call_command("seed_british_school_2026_08")

    second_state = {
        "celky": list(Celok.objects.order_by("pk").values()),
        "prevadzky": list(Prevadzka.objects.order_by("pk").values()),
        "connections": list(EdupageConnection.objects.order_by("pk").values()),
        "routes": list(DeliveryRoute.objects.order_by("pk").values()),
    }
    assert second_state == first_state
    assert (
        EdupageConnection.objects.filter(mealsguest_url=BRITISH_SCHOOL_URL).count() == 1
    )
    assert DeliveryRoute.objects.filter(name="British School").count() == 1


@pytest.mark.django_db
def test_seed_british_school_dry_run_rolls_back():
    _seed_trasa_extra_block()

    call_command("seed_british_school_2026_08", "--dry-run")

    assert not Celok.objects.filter(nazov="British School").exists()
    assert not EdupageConnection.objects.filter(
        mealsguest_url=BRITISH_SCHOOL_URL
    ).exists()
    assert not DeliveryRoute.objects.filter(name="British School").exists()
