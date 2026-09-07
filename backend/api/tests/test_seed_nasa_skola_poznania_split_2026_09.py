import pytest
from django.core.management import call_command

from api.models import Celok, EdupageConnection, Prevadzka


@pytest.mark.django_db
def test_seed_nasa_skola_poznania_assigns_fourth_grade_to_house_b():
    """EduPage's 4. ročník payer row belongs to dom B, not dom A."""
    celok = Celok.objects.create(nazov="Naša škola poznania")
    connection = EdupageConnection.objects.create(
        name="Naša škola poznania",
        mealsguest_url="https://nsp.edupage.org/menu/mealsGuest?id=test",
    )
    Prevadzka.objects.create(
        celok=celok,
        nazov="Naša škola poznania A",
        edupage_connection=connection,
    )
    Prevadzka.objects.create(celok=celok, nazov="Naša škola poznania B")

    call_command("seed_nasa_skola_poznania_split_2026_09")

    dom_a = celok.prevadzky.get(nazov="Naša škola poznania A")
    dom_b = celok.prevadzky.get(nazov="Naša škola poznania B")
    assert dom_a.edupage_connection == connection
    assert dom_a.edupage_match == "1.-3.ročník"
    assert dom_b.edupage_connection == connection
    assert dom_b.edupage_match == "4. ročník"
