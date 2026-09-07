from datetime import date

import pytest
from django.core.management import call_command

from api.models import Celok, DailyOrder, EdupageConnection, Prevadzka


def _order(subdomain: str, flags: dict) -> DailyOrder:
    celok = Celok.objects.create(nazov=subdomain)
    connection = EdupageConnection.objects.create(
        name=subdomain,
        mealsguest_url=f"https://{subdomain}.edupage.org/menu/mealsGuest?id=test",
    )
    prevadzka = Prevadzka.objects.create(
        celok=celok, nazov=subdomain, edupage_connection=connection
    )
    return DailyOrder.objects.create(
        prevadzka=prevadzka, date=date(2026, 9, 7), scrape_flags=flags
    )


@pytest.mark.django_db
def test_clear_confirmed_uncertain_flags_only_for_confirmed_edupage_feeds():
    confirmed = [
        _order(
            "rozmanita",
            {"attention": ["keep this"], "uncertain_diets": ["A:NoMO→NO MILK"]},
        ),
        _order("dobrodruzstvo", {"uncertain_diets": ["B:bezlak→NO MILK"]}),
        _order("szsfan", {"uncertain_diets": ["C:HIT…"]}),
        _order("fantastickaskolka", {"uncertain_diets": ["B:nM/nG"]}),
        _order("skolickams", {"uncertain_diets": ["D:ŠPECI"]}),
    ]
    other = _order("skolkacvernicka", {"uncertain_diets": ["X:unknown"]})

    call_command("clear_confirmed_edupage_uncertain_flags")

    for order in confirmed:
        order.refresh_from_db()
        assert "uncertain_diets" not in order.scrape_flags
    assert confirmed[0].scrape_flags["attention"] == ["keep this"]
    other.refresh_from_db()
    assert other.scrape_flags["uncertain_diets"] == ["X:unknown"]
