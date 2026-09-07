"""
Plošná kontrola prístupu na VŠETKY API endpointy × všetky role (#482–#484).

Rolový systém prepol permission triedu na ~30 viewsetoch. Bodové testy overia
tie, na ktoré si spomeniem; tento test prejde všetko, čo je v urlconfe, aby sa
nestalo, že sa niekde ticho rozbije endpoint, ktorého som sa ani nedotkol.

Stráži dve veci:

1. **Nikdy 5xx.** Rola nesmie zhodiť server — ani nečakaná kombinácia. Toto je
   hlavná poistka proti „spadne appka".
2. **Admin plocha odmieta klienta aj neprihláseného.** Nie ako zoznam
   výnimiek, ale pravidlom nad celou `/api/admin/` plochou.

Zámerne sa nefixujú konkrétne stavové kódy pre povolené prípady: 200, 400 aj
404 sú legitímne (chýbajúci parameter, prázdne dáta). Test sa pýta na
prístup, nie na obsah.
"""

from __future__ import annotations

import functools
import re

import pytest
from django.contrib.auth.models import User
from django.urls import get_resolver
from rest_framework.test import APIClient

from api import roles
from api.models import UserProfile

pytestmark = pytest.mark.django_db


@functools.lru_cache(maxsize=1)
def _api_routes() -> tuple[str, ...]:
    """Zoznamové API cesty — bez detailov (`<pk>`) a bez format prípon."""

    def walk(resolver, prefix=""):
        for pattern in resolver.url_patterns:
            if hasattr(pattern, "url_patterns"):
                yield from walk(pattern, prefix + str(pattern.pattern))
            else:
                yield prefix + str(pattern.pattern)

    out = set()
    for raw in walk(get_resolver()):
        if not raw.startswith("api/"):
            continue
        if "format" in raw or "<" in raw or "(?P<" in raw:
            continue
        path = "/" + re.sub(r"[\^$]", "", raw)
        if not path.endswith("/"):
            path += "/"
        out.add(path)
    return tuple(sorted(out))


# Zámerne funkcia, nie konštanta: stavať zoznam pri importe znamená siahnuť na
# URL resolver už pri zbere testov, čo rozbíja testy, ktoré si prepínajú
# `DEBUG` cez `override_settings` (`tests/test_security.py`).

#: Katalógy pod `/api/admin/` prefixom, ktoré ČÍTA aj klient — objednávkový
#: formulár bez nich nevie vykresliť porcie ani jedlá. Je to zámer spred rolí
#: („non-staff see only active entries and cannot write"), nie diera; test
#: nižšie preto stráži, že zápis do nich klientovi zakázaný ostáva.
CLIENT_READABLE = {
    "/api/admin/meal-templates/",
    "/api/admin/portion-types/",
}

#: Plocha, na ktorú smie kuchyňa — prehľad nakladania, jeho tlač a klikací
#: zoznam "spolu/zvlášť" diét (#568), ktorý si vyklikáva priamo šéfkuchár.
KUCHYNA_ALLOWED = {
    "/api/kuchyna/loading/",
    "/api/admin/meal-plans/gramage-dashboard/",
    "/api/admin/meal-plans/gramage-dashboard-pdf/",
    "/api/admin/diet-component-merge/board/",
    "/api/admin/diet-component-merge/toggle/",
}

#: Endpointy, ktoré sú verejné zámerne — prihlasovanie a údaje pre login obrazovku.
PUBLIC = {
    "/api/token/",
    "/api/token/refresh/",
    "/api/token/logout/",
    "/api/password-reset/",
    "/api/password-reset/confirm/",
    "/api/admin/global-settings/",
    "/api/health/",
    "/api/schema/",
    "/api/vapid-public-key/",
}


def _make(role: str | None) -> APIClient:
    client = APIClient()
    if role is None:
        return client
    user = User.objects.create_user(
        username=f"{role}@sweep.test",
        email=f"{role}@sweep.test",
        password="x",
        is_staff=role in roles.STAFF_ROLES,
        is_superuser=role == roles.SUPERADMIN,
    )
    profile = UserProfile(user=user, role=role)
    profile._skip_default_facility = True
    profile.save()
    client.force_authenticate(user=user)
    return client


ALL_ROLES = [None, roles.KLIENT, roles.KUCHYNA, roles.ADMIN, roles.SUPERADMIN]


def test_sweep_covers_a_meaningful_number_of_routes():
    """Poistka, aby test nezostal ticho prázdny, keby sa zmenil urlconf."""
    routes = _api_routes()
    assert len(routes) >= 30, routes


@pytest.mark.parametrize("role", ALL_ROLES, ids=lambda r: r or "anonym")
def test_no_route_ever_returns_5xx(role):
    """Žiadna rola nesmie zhodiť žiadny endpoint."""
    client = _make(role)
    crashes = []
    for path in _api_routes():
        for method in ("get", "post"):
            try:
                response = getattr(client, method)(path, {}, format="json")
            except Exception as exc:  # noqa: BLE001 - chceme vidieť aj výnimku
                crashes.append(f"{method.upper()} {path} → výnimka {exc!r}")
                continue
            if response.status_code >= 500:
                crashes.append(f"{method.upper()} {path} → {response.status_code}")
    assert not crashes, "5xx alebo výnimka:\n" + "\n".join(crashes)


@pytest.mark.parametrize("role", [None, roles.KLIENT], ids=["anonym", "klient"])
def test_admin_surface_is_closed_to_clients(role):
    """Celá `/api/admin/` plocha odmieta klienta aj neprihláseného."""
    client = _make(role)
    leaks = []
    for path in _api_routes():
        if not path.startswith("/api/admin/"):
            continue
        if path in PUBLIC or path in CLIENT_READABLE:
            continue
        response = client.get(path)
        if response.status_code not in (401, 403):
            leaks.append(f"GET {path} → {response.status_code}")
    assert not leaks, "admin endpoint pustil klienta:\n" + "\n".join(leaks)


@pytest.mark.parametrize("path", sorted(CLIENT_READABLE))
def test_client_readable_catalogues_stay_read_only(path):
    """Katalóg smie klient čítať, ale nie meniť — to je celá podmienka výnimky."""
    client = _make(roles.KLIENT)
    assert client.get(path).status_code == 200
    assert client.post(path, {}, format="json").status_code == 403


def test_client_sees_only_active_catalogue_entries():
    """Filtrovanie neaktívnych položiek viselo na `is_staff`; po prechode na
    rolu musí platiť ďalej, inak by klient dostal do formulára zrušené jedlá."""
    from api.models import MealTemplate

    # Referenčné dáta v testovej DB nie sú, tak si katalóg vyrobíme.
    visible = MealTemplate.objects.create(
        category="soup", name="Viditeľná", base_weight_grams=100, is_active=True
    )
    hidden = MealTemplate.objects.create(
        category="soup", name="Zrušená", base_weight_grams=100, is_active=False
    )

    client = _make(roles.KLIENT)
    client_ids = [row["id"] for row in client.get("/api/admin/meal-templates/").json()]
    assert visible.id in client_ids
    assert hidden.id not in client_ids

    admin = _make(roles.ADMIN)
    admin_ids = [row["id"] for row in admin.get("/api/admin/meal-templates/").json()]
    assert hidden.id in admin_ids


def test_kuchyna_reaches_only_its_own_surface():
    """Kuchyňa smie na prehľad nakladania — a inde na admin ploche nie."""
    client = _make(roles.KUCHYNA)
    leaks = []
    for path in _api_routes():
        if not path.startswith("/api/admin/"):
            continue
        if path in PUBLIC or path in CLIENT_READABLE or path in KUCHYNA_ALLOWED:
            continue
        response = client.get(path)
        if response.status_code not in (401, 403):
            leaks.append(f"GET {path} → {response.status_code}")
    assert not leaks, "kuchyňa sa dostala do admin sekcie:\n" + "\n".join(leaks)

    # A na svoju plochu sa dostane.
    assert client.get("/api/kuchyna/loading/?date=2026-08-18").status_code == 200
    assert (
        client.get(
            "/api/admin/meal-plans/gramage-dashboard/?date=2026-08-18"
        ).status_code
        == 200
    )


def test_superadmin_reaches_the_whole_admin_surface():
    """Najvyššia rola nesmie nikde naraziť na 403 — inak si niekto zamkol konzolu."""
    client = _make(roles.SUPERADMIN)
    blocked = []
    for path in _api_routes():
        if not path.startswith("/api/admin/"):
            continue
        response = client.get(path)
        if response.status_code == 403:
            blocked.append(f"GET {path} → 403")
    assert not blocked, "superadmin bol odmietnutý:\n" + "\n".join(blocked)
