from io import StringIO

import pytest
from django.core.management import call_command

from api.models import Celok, Prevadzka


@pytest.mark.django_db
def test_delivery_layout_does_not_resurrect_retired_edulienka_default():
    """Regression test: seed_real_delivery_layout previously targeted the
    pre-split "MŠ Edulienka" name and unconditionally set is_active=True on
    whatever prevádzka it matched. Once seed_prevadzky_edupage.SPLITS started
    actually splitting Edulienka (see test_seed_prevadzky_edupage.py), this
    resurrected the retired default prevádzka on every reseed, leaving 3
    active prevádzky under the celok instead of 2 and breaking the
    single-active-prevádzka assumption the scrape task relies on."""
    celok = Celok.objects.create(nazov="MŠ Edulienka")
    Prevadzka.objects.create(
        celok=celok,
        nazov="MŠ Edulienka",
        billing_portion_coefficients={"Predškolák": "1.25"},
    )

    call_command("seed_prevadzky_edupage", stdout=StringIO(), stderr=StringIO())
    call_command("seed_real_delivery_layout", stdout=StringIO())

    prevadzky = {p.nazov: p for p in Prevadzka.objects.filter(celok=celok)}
    assert prevadzky["MŠ Edulienka"].is_active is False
    assert prevadzky["Palisády"].is_active is True
    assert prevadzky["Stupava"].is_active is True
    assert prevadzky["Palisády"].delivery_route is not None
    assert prevadzky["Stupava"].delivery_route is not None
