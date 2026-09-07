"""Testy prístupu prihlásenia k prevádzkam a výberu prevádzky pri objednávaní."""

import datetime

import pytest
from django.contrib.auth.models import User

from api.models import (
    Celok,
    DailyOrder,
    Prevadzka,
    ProfileCelokAccess,
    ProfilePrevadzkaAccess,
    UserProfile,
)
from api.services.prevadzka_service import (
    PrevadzkaNedostupna,
    PrevadzkaNejednoznacna,
    dostupne_prevadzky,
    vyber_prevadzku,
)


@pytest.fixture
def celok(db):
    return Celok.objects.create(nazov="Jolly")


@pytest.fixture
def jolly(celok):
    return [
        Prevadzka.objects.create(celok=celok, nazov=f"Jolly {i}", sort_order=i)
        for i in (1, 2, 3)
    ]


def _profile(email, celok=None):
    user = User.objects.create_user(username=email, email=email)
    profile = UserProfile(user=user, company_name=email)
    profile._skip_default_facility = True
    profile.save()
    if celok is not None:
        ProfileCelokAccess.objects.create(profile=profile, celok=celok)
    return user, profile


@pytest.mark.django_db
class TestDostupnePrevadzky:
    def test_empty_m2m_means_whole_celok(self, celok, jolly):
        """Prázdny výber = všetky prevádzky celku, nie žiadna."""
        user, _ = _profile("eva@example.com", celok)
        assert dostupne_prevadzky(user).count() == 3

    def test_explicit_subset_restricts(self, celok, jolly):
        user, profile = _profile("jano@example.com", celok)
        profile.celok_accesses.all().delete()
        ProfilePrevadzkaAccess.objects.create(profile=profile, prevadzka=jolly[1])
        assert [p.nazov for p in dostupne_prevadzky(user)] == ["Jolly 2"]

    def test_inactive_prevadzka_excluded(self, celok, jolly):
        user, _ = _profile("eva@example.com", celok)
        jolly[0].is_active = False
        jolly[0].save()
        assert dostupne_prevadzky(user).count() == 2

    def test_user_without_profile_has_none(self, db):
        user = User.objects.create_user(username="x@example.com", email="x@example.com")
        assert dostupne_prevadzky(user).count() == 0


@pytest.mark.django_db
class TestVyberPrevadzku:
    def test_single_prevadzka_needs_no_choice(self, celok):
        """Jedna prevádzka → klient sa nič nevyberá, UI ostáva ako doteraz."""
        Prevadzka.objects.create(celok=celok, nazov="Jolly 1")
        user, _ = _profile("jano@example.com", celok)
        assert vyber_prevadzku(user).nazov == "Jolly 1"

    def test_multiple_prevadzky_requires_explicit_choice(self, celok, jolly):
        user, _ = _profile("eva@example.com", celok)
        with pytest.raises(PrevadzkaNejednoznacna):
            vyber_prevadzku(user)

    def test_explicit_choice_accepted(self, celok, jolly):
        user, _ = _profile("eva@example.com", celok)
        assert vyber_prevadzku(user, jolly[2].pk).nazov == "Jolly 3"

    def test_choice_outside_access_rejected(self, celok, jolly):
        """Nesmieš objednať za prevádzku, ku ktorej nemáš prístup."""
        user, profile = _profile("jano@example.com", celok)
        profile.celok_accesses.all().delete()
        ProfilePrevadzkaAccess.objects.create(profile=profile, prevadzka=jolly[0])
        with pytest.raises(PrevadzkaNedostupna):
            vyber_prevadzku(user, jolly[2].pk)

    def test_choice_from_foreign_celok_rejected(self, celok, jolly, db):
        iny = Celok.objects.create(nazov="Rozmanitá")
        cudzia = Prevadzka.objects.create(celok=iny, nazov="Rozmanitá Škola")
        user, _ = _profile("eva@example.com", celok)
        with pytest.raises(PrevadzkaNedostupna):
            vyber_prevadzku(user, cudzia.pk)

    def test_no_prevadzka_at_all_rejected(self, celok):
        user, _ = _profile("nikto@example.com", celok)
        with pytest.raises(PrevadzkaNedostupna):
            vyber_prevadzku(user)


@pytest.mark.django_db
class TestPrevadzkaEndpoint:
    def test_lists_only_accessible_prevadzky(self, api_client, celok, jolly):
        user, profile = _profile("jano@example.com", celok)
        profile.celok_accesses.all().delete()
        ProfilePrevadzkaAccess.objects.create(profile=profile, prevadzka=jolly[0])
        api_client.force_authenticate(user=user)
        response = api_client.get("/api/prevadzky/")
        assert response.status_code == 200
        assert [p["nazov"] for p in response.json()] == ["Jolly 1"]

    def test_empty_selection_lists_whole_celok(self, api_client, celok, jolly):
        user, _ = _profile("eva@example.com", celok)
        api_client.force_authenticate(user=user)
        response = api_client.get("/api/prevadzky/")
        assert len(response.json()) == 3

    def test_requires_auth(self, api_client):
        assert api_client.get("/api/prevadzky/").status_code in (401, 403)

    def test_exposes_visible_menu_settings(self, api_client, celok):
        # `on_prevadzka_saved` pri vytvorení prepíše visible_menus/visible_meals
        # defaultmi, takže vlastné hodnoty treba nastaviť až po vzniku záznamu.
        prevadzka = Prevadzka.objects.create(celok=celok, nazov="Jolly 1")
        prevadzka.visible_menus = ["A", "B", "V"]
        prevadzka.visible_meals = ["breakfast", "lunch", "olovrant"]
        prevadzka.pack_separately_enabled = True
        prevadzka.save()
        user, _ = _profile("eva@example.com", celok)
        api_client.force_authenticate(user=user)

        response = api_client.get("/api/prevadzky/")

        assert response.status_code == 200
        assert response.json() == [
            {
                "id": prevadzka.id,
                "nazov": "Jolly 1",
                "adresa": "",
                "celok": "Jolly",
                "visible_menus": ["A", "B", "V"],
                "menu_day_restrictions": {},
                "visible_meals": ["breakfast", "lunch", "olovrant"],
                "meal_day_restrictions": {},
                "visible_diets": [],
                "visible_portion_types": [],
                "pack_separately_enabled": True,
            }
        ]

    def test_exposes_menu_day_restrictions_when_set(self, api_client, celok):
        # napr. "menu B len v piatok"
        prevadzka = Prevadzka.objects.create(celok=celok, nazov="Jolly 1")
        prevadzka.visible_menus = ["A", "B"]
        prevadzka.menu_day_restrictions = {"B": [5]}
        prevadzka.save()
        user, _ = _profile("eva@example.com", celok)
        api_client.force_authenticate(user=user)

        response = api_client.get("/api/prevadzky/")

        assert response.status_code == 200
        assert response.json()[0]["menu_day_restrictions"] == {"B": [5]}

    def test_exposes_meal_day_restrictions_when_set(self, api_client, celok):
        # napr. "raňajky len v piatok"
        prevadzka = Prevadzka.objects.create(celok=celok, nazov="Jolly 1")
        prevadzka.meal_day_restrictions = {"breakfast": [5]}
        prevadzka.save()
        user, _ = _profile("eva@example.com", celok)
        api_client.force_authenticate(user=user)

        response = api_client.get("/api/prevadzky/")

        assert response.status_code == 200
        assert response.json()[0]["meal_day_restrictions"] == {"breakfast": [5]}


@pytest.mark.django_db
class TestDailyOrderByDatePrevadzka:
    def test_multi_prevadzka_by_date_requires_prevadzka_param(
        self, api_client, celok, jolly
    ):
        user, _ = _profile("multi@example.com", celok)
        target_date = datetime.date(2099, 7, 10)
        DailyOrder.objects.create(
            user=user,
            prevadzka=jolly[0],
            date=target_date,
            data={"lunch": {"Škôlka": {"menuCounts": {"A": 1}, "diets": {}}}},
        )
        DailyOrder.objects.create(
            user=user,
            prevadzka=jolly[1],
            date=target_date,
            data={"lunch": {"Škôlka": {"menuCounts": {"A": 2}, "diets": {}}}},
        )

        api_client.force_authenticate(user=user)

        response = api_client.get(f"/api/orders/by-date/{target_date}/")

        assert response.status_code == 400
        assert "prevadzka" in response.json()

    def test_multi_prevadzka_by_date_filters_selected_prevadzka(
        self, api_client, celok, jolly
    ):
        user, _ = _profile("multi-selected@example.com", celok)
        target_date = datetime.date(2099, 7, 10)
        DailyOrder.objects.create(
            user=user,
            prevadzka=jolly[0],
            date=target_date,
            data={"lunch": {"Škôlka": {"menuCounts": {"A": 1}, "diets": {}}}},
        )
        DailyOrder.objects.create(
            user=user,
            prevadzka=jolly[1],
            date=target_date,
            data={"lunch": {"Škôlka": {"menuCounts": {"A": 2}, "diets": {}}}},
        )

        api_client.force_authenticate(user=user)

        response = api_client.get(
            f"/api/orders/by-date/{target_date}/?prevadzka={jolly[1].pk}"
        )

        assert response.status_code == 200
        assert response.json()["data"]["lunch"]["Škôlka"]["menuCounts"]["A"] == 2


@pytest.mark.django_db
class TestProfileSignalAndSaveGuards:
    """Regresie #1 (signál) a #3 (save)."""

    def test_same_company_name_profiles_get_separate_celoky(self):
        """Dva profily s rovnakým company_name sa NEsmú zlúčiť do jedného celku."""
        u1 = User.objects.create_user(username="a@e.com", email="a@e.com")
        u2 = User.objects.create_user(username="b@e.com", email="b@e.com")
        p1 = UserProfile.objects.create(user=u1, company_name="Rovnaký názov")
        p2 = UserProfile.objects.create(user=u2, company_name="Rovnaký názov")
        assert p1.primary_celok() is not None
        assert p2.primary_celok() is not None
        assert p1.primary_celok() != p2.primary_celok()

    def test_daily_order_without_prevadzka_raises_for_multi(self, celok, jolly):
        """Objednávka bez prevádzky pre multi-prevádzka login = chyba, nie tichý None."""
        from datetime import date

        from api.models import DailyOrder

        user, profile = _profile("multi@example.com", celok)  # 3 prevádzky (jolly)
        with pytest.raises(ValueError):
            DailyOrder.objects.create(user=user, date=date(2026, 7, 10), data={})

    def test_daily_order_autofills_single_prevadzka(self, celok):
        from datetime import date

        from api.models import DailyOrder, Prevadzka

        p = Prevadzka.objects.create(celok=celok, nazov="Jediná")
        user, _ = _profile("single@example.com", celok)
        order = DailyOrder.objects.create(user=user, date=date(2026, 7, 10), data={})
        assert order.prevadzka_id == p.id
