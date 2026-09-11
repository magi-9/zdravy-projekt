"""
Comprehensive tests for auto-order generation and related logic.

Covers:
- Auto-order service functions (_is_order_empty, _next_workday, _last_non_empty_order, _build_auto_data)
- apply_auto_orders() service behavior
- PlannedOrdersViewSet template selection logic
- AdminAutoOrderViewSet trigger endpoint
"""

import datetime
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status

from api.models import (
    Celok,
    ClosedDay,
    DailyOrder,
    EventLog,
    Prevadzka,
    ProfileCelokAccess,
    ProfilePrevadzkaAccess,
    UserProfile,
)
from api.services import (
    _build_auto_data,
    _is_order_empty,
    _last_non_empty_order,
    _next_workday,
    apply_auto_orders,
)

pytestmark = pytest.mark.integration


NON_EMPTY_DATA = {
    "breakfast": {"Dospelý": {"menuCounts": {"A": 1}, "diets": {}}},
    "lunch": {"Dospelý": {"menuCounts": {"B": 2}, "diets": {}}},
    "olovrant": {},
}

NON_EMPTY_DATA_WITH_PACK_SEPARATELY = {
    "breakfast": {
        "Dospelý": {
            "menuCounts": {"A": 1},
            "diets": {},
            "packSeparately": {"menus": {"A": 1}},
        }
    },
    "lunch": {
        "Dospelý": {
            "menuCounts": {"B": 2},
            "diets": {"Bez lepku": 1},
            "packSeparately": {"menus": {"B": 1}, "diets": {"Bez lepku": 1}},
        }
    },
    "olovrant": {},
}

EMPTY_DATA = {
    "breakfast": {"Dospelý": {"menuCounts": {"A": 0}, "diets": {}}},
    "lunch": {},
    "olovrant": {},
}

# Reference dates: all confirmed weekdays/weekends for predictable tests
MONDAY = datetime.date(2025, 1, 6)
TUESDAY = datetime.date(2025, 1, 7)
WEDNESDAY = datetime.date(2025, 1, 8)
THURSDAY = datetime.date(2025, 1, 9)
FRIDAY = datetime.date(2025, 1, 10)
SATURDAY = datetime.date(2025, 1, 11)
SUNDAY = datetime.date(2025, 1, 12)
NEXT_MONDAY = datetime.date(2025, 1, 13)


def _client_user(**kwargs):
    """User + UserProfile (a tým celok + default prevádzka cez signál).

    Objednávky sa vedú per prevádzka, takže klient bez profilu nemá kam objednávať.
    V produkcii profil vzniká pri založení klienta.
    """
    from api.models import UserProfile

    user = User.objects.create_user(**kwargs)
    if not kwargs.get("is_staff"):
        UserProfile.objects.get_or_create(
            user=user, defaults={"company_name": user.email}
        )
    return user


@pytest.mark.django_db
class TestNextWorkday:
    """Test _next_workday() pure function."""

    def test_monday_returns_tuesday(self):
        """Monday → Tuesday"""
        assert _next_workday(MONDAY) == TUESDAY

    def test_friday_returns_next_monday(self):
        """Friday → following Monday"""
        assert _next_workday(FRIDAY) == NEXT_MONDAY

    def test_saturday_returns_next_monday(self):
        """Saturday → following Monday"""
        assert _next_workday(SATURDAY) == NEXT_MONDAY

    def test_sunday_returns_next_monday(self):
        """Sunday → following Monday"""
        assert _next_workday(SUNDAY) == NEXT_MONDAY

    def test_thursday_returns_friday(self):
        """Thursday → Friday"""
        assert _next_workday(THURSDAY) == FRIDAY

    def test_always_returns_weekday(self):
        """Result is always a weekday (Mon-Fri)."""
        for offset in range(30):
            d = MONDAY + datetime.timedelta(days=offset)
            result = _next_workday(d)
            assert (
                result.weekday() < 5
            ), f"_next_workday({d}) = {result} (weekday={result.weekday()})"


@pytest.mark.django_db
class TestIsOrderEmpty:
    """Test _is_order_empty() helper."""

    def test_empty_dict_is_empty(self):
        """Empty dict returns True."""
        assert _is_order_empty({}) is True

    def test_all_zero_portions_is_empty(self):
        """Order with all zero menuCounts returns True."""
        assert _is_order_empty(EMPTY_DATA) is True

    def test_any_positive_portion_not_empty(self):
        """Order with any positive count returns False."""
        assert _is_order_empty(NON_EMPTY_DATA) is False

    def test_single_meal_positive_not_empty(self):
        """Single meal with positive count returns False."""
        data = {"lunch": {"Dospelý": {"menuCounts": {"A": 3}}}}
        assert _is_order_empty(data) is False

    def test_mixed_zero_and_positive_not_empty(self):
        """Mix of zero and positive portions returns False."""
        data = {
            "breakfast": {"Dospelý": {"menuCounts": {"A": 0}}},
            "lunch": {"Dospelý": {"menuCounts": {"B": 1}}},
        }
        assert _is_order_empty(data) is False

    def test_flat_shape_not_empty(self):
        """Flat shape (no category level) with positive count returns False."""
        data = {"lunch": {"menuCounts": {"A": 1}}}
        assert _is_order_empty(data) is False

    def test_flat_shape_zero_is_empty(self):
        """Flat shape with zero counts returns True."""
        data = {"breakfast": {"menuCounts": {"A": 0}}}
        assert _is_order_empty(data) is True


@pytest.mark.django_db
class TestLastNonEmptyOrder:
    """Test _last_non_empty_order() service function."""

    def test_no_history_returns_none(self, user):
        """User with no prior orders returns None."""
        result = _last_non_empty_order(user, TUESDAY)
        assert result is None

    def test_finds_last_non_empty_order(self, user):
        """Returns the most recent non-empty order before given date."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)
        DailyOrder.objects.create(user=user, date=TUESDAY, data=EMPTY_DATA)

        result = _last_non_empty_order(user, WEDNESDAY)
        assert result is not None
        assert result.date == MONDAY

    def test_skips_empty_orders(self, user):
        """Returns the last non-empty order, skipping empty ones."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)
        DailyOrder.objects.create(user=user, date=TUESDAY, data=EMPTY_DATA)
        DailyOrder.objects.create(user=user, date=WEDNESDAY, data=EMPTY_DATA)

        result = _last_non_empty_order(user, THURSDAY)
        assert result is not None
        assert result.date == MONDAY

    def test_respects_before_date_boundary(self, user):
        """Does not return orders on or after the before_date."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)
        DailyOrder.objects.create(user=user, date=TUESDAY, data=NON_EMPTY_DATA)

        result = _last_non_empty_order(user, TUESDAY)
        assert result is not None
        assert result.date == MONDAY  # Excludes TUESDAY (boundary)

    def test_returns_most_recent_before_date(self, user):
        """With multiple non-empty orders, returns the most recent one before date."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)
        DailyOrder.objects.create(user=user, date=WEDNESDAY, data=NON_EMPTY_DATA)
        DailyOrder.objects.create(user=user, date=FRIDAY, data=NON_EMPTY_DATA)

        result = _last_non_empty_order(user, SATURDAY)
        assert result.date == FRIDAY


@pytest.mark.django_db
class TestBuildAutoData:
    """Test _build_auto_data() meal filtering function."""

    def test_all_meals_when_visible_meals_empty(self):
        """When visible_meals is empty, all meals are copied."""
        auto_data = _build_auto_data(DailyOrder(data=NON_EMPTY_DATA), visible_meals=[])

        assert "breakfast" in auto_data
        assert "lunch" in auto_data
        assert "olovrant" in auto_data
        assert auto_data["breakfast"] == NON_EMPTY_DATA["breakfast"]
        assert auto_data["lunch"] == NON_EMPTY_DATA["lunch"]

    def test_single_meal_visible(self):
        """When only lunch is visible, only lunch is copied."""
        auto_data = _build_auto_data(
            DailyOrder(data=NON_EMPTY_DATA), visible_meals=["lunch"]
        )

        assert auto_data["breakfast"] == {}
        assert auto_data["lunch"] == NON_EMPTY_DATA["lunch"]
        assert auto_data["olovrant"] == {}

    def test_multiple_meals_visible(self):
        """When breakfast and lunch are visible."""
        auto_data = _build_auto_data(
            DailyOrder(data=NON_EMPTY_DATA), visible_meals=["breakfast", "lunch"]
        )

        assert auto_data["breakfast"] == NON_EMPTY_DATA["breakfast"]
        assert auto_data["lunch"] == NON_EMPTY_DATA["lunch"]
        assert auto_data["olovrant"] == {}

    def test_copies_empty_meals_when_visible(self):
        """Empty meals are still included if visible_meals allows them."""
        auto_data = _build_auto_data(
            DailyOrder(data=NON_EMPTY_DATA), visible_meals=["olovrant"]
        )

        assert auto_data["olovrant"] == {}  # Empty but included
        assert auto_data["breakfast"] == {}
        assert auto_data["lunch"] == {}

    def test_pack_separately_is_carried_forward(self):
        auto_data = _build_auto_data(
            DailyOrder(data=NON_EMPTY_DATA_WITH_PACK_SEPARATELY), visible_meals=[]
        )

        assert (
            auto_data["lunch"]["Dospelý"]["packSeparately"]
            == NON_EMPTY_DATA_WITH_PACK_SEPARATELY["lunch"]["Dospelý"]["packSeparately"]
        )

    def test_breakfast_source_lunch_copies_previous_lunch_into_breakfast(self):
        """Keď má šablónová prevádzka `auto_order_breakfast_source='lunch'`, raňajky
        v auto-objednávke sa naplnia obedom zo šablóny, nie raňajkami (Bystrá #TBD)."""
        prevadzka = Prevadzka.objects.create(
            celok=Celok.objects.create(nazov="Bystrá test celok"),
            nazov="Bystrá test prevádzka",
            auto_order_breakfast_source="lunch",
        )
        auto_data = _build_auto_data(
            DailyOrder(data=NON_EMPTY_DATA, prevadzka=prevadzka),
            visible_meals=[],
        )

        assert auto_data["breakfast"] == NON_EMPTY_DATA["lunch"]
        assert auto_data["lunch"] == NON_EMPTY_DATA["lunch"]

    def test_breakfast_source_default_keeps_breakfast_to_breakfast(self):
        """Default (bez `auto_order_breakfast_source` override) sa nemení: raňajky
        z raňajok, obed z obeda — existujúce správanie ostáva netknuté."""
        prevadzka = Prevadzka.objects.create(
            celok=Celok.objects.create(nazov="Default test celok"),
            nazov="Default test prevádzka",
        )
        auto_data = _build_auto_data(
            DailyOrder(data=NON_EMPTY_DATA, prevadzka=prevadzka),
            visible_meals=[],
        )

        assert auto_data["breakfast"] == NON_EMPTY_DATA["breakfast"]
        assert auto_data["lunch"] == NON_EMPTY_DATA["lunch"]

    def test_only_visible_portion_types_are_copied(self):
        data = {
            "breakfast": {
                "Škôlka": {"menuCounts": {"A": 2}, "diets": {}},
                "Dospelý": {"menuCounts": {"A": 1}, "diets": {}},
            },
            "lunch": {},
            "olovrant": {},
        }

        auto_data = _build_auto_data(
            DailyOrder(data=data),
            visible_meals=[],
            visible_portion_types=["Škôlka"],
        )

        assert set(auto_data["breakfast"]) == {"Škôlka"}

    def test_target_date_none_skips_day_restrictions(self):
        """Bez `target_date` (staršie volania/testy) sa deň-špecifické
        obmedzenia neaplikujú — pôvodné správanie ostáva netknuté."""
        prevadzka = Prevadzka.objects.create(
            celok=Celok.objects.create(nazov="Day-restriction test celok"),
            nazov="Day-restriction test prevádzka",
            visible_menus=["A", "B"],
            menu_day_restrictions={"B": [5]},
        )
        auto_data = _build_auto_data(
            DailyOrder(data=NON_EMPTY_DATA, prevadzka=prevadzka), visible_meals=[]
        )
        assert auto_data["lunch"] == NON_EMPTY_DATA["lunch"]

    def test_meal_restricted_on_target_date_is_dropped(self):
        """Raňajky zakázané v utorok (meal_day_restrictions) — auto-
        -objednávka na utorok raňajky vôbec neskopíruje, hoci sú vo
        visible_meals aj v šablóne."""
        prevadzka = Prevadzka.objects.create(
            celok=Celok.objects.create(nazov="Meal-restriction test celok"),
            nazov="Meal-restriction test prevádzka",
            meal_day_restrictions={"breakfast": [5]},  # len piatok
        )
        auto_data = _build_auto_data(
            DailyOrder(data=NON_EMPTY_DATA, prevadzka=prevadzka),
            visible_meals=[],
            target_date=TUESDAY,
        )
        assert auto_data["breakfast"] == {}
        assert auto_data["lunch"] == NON_EMPTY_DATA["lunch"]

    def test_meal_allowed_on_its_restricted_day_is_kept(self):
        prevadzka = Prevadzka.objects.create(
            celok=Celok.objects.create(nazov="Meal-restriction ok test celok"),
            nazov="Meal-restriction ok test prevádzka",
            meal_day_restrictions={"breakfast": [5]},
        )
        auto_data = _build_auto_data(
            DailyOrder(data=NON_EMPTY_DATA, prevadzka=prevadzka),
            visible_meals=[],
            target_date=FRIDAY,
        )
        assert auto_data["breakfast"] == NON_EMPTY_DATA["breakfast"]

    def test_menu_restricted_on_target_date_is_redirected_to_the_allowed_menu(self):
        """Menu B len v piatok — v utorok šablóna s menu B v obede preklopí
        počty do menu A (jediné dnes povolené), namiesto toho, aby zmizli."""
        prevadzka = Prevadzka.objects.create(
            celok=Celok.objects.create(nazov="Menu-redirect test celok"),
            nazov="Menu-redirect test prevádzka",
            visible_menus=["A", "B"],
            menu_day_restrictions={"B": [5]},
        )
        data = {
            "breakfast": {},
            "lunch": {"Dospelý": {"menuCounts": {"B": 2}, "diets": {}}},
            "olovrant": {},
        }
        auto_data = _build_auto_data(
            DailyOrder(data=data, prevadzka=prevadzka),
            visible_meals=[],
            target_date=TUESDAY,
        )
        assert auto_data["lunch"]["Dospelý"]["menuCounts"] == {"A": 2}

    def test_menu_allowed_on_its_restricted_day_is_not_redirected(self):
        prevadzka = Prevadzka.objects.create(
            celok=Celok.objects.create(nazov="Menu-redirect ok test celok"),
            nazov="Menu-redirect ok test prevádzka",
            visible_menus=["A", "B"],
            menu_day_restrictions={"B": [5]},
        )
        data = {
            "breakfast": {},
            "lunch": {"Dospelý": {"menuCounts": {"B": 2}, "diets": {}}},
            "olovrant": {},
        }
        auto_data = _build_auto_data(
            DailyOrder(data=data, prevadzka=prevadzka),
            visible_meals=[],
            target_date=FRIDAY,
        )
        assert auto_data["lunch"]["Dospelý"]["menuCounts"] == {"B": 2}

    def test_menu_redirect_merges_into_existing_fallback_count(self):
        """Ak šablóna má v tej istej kategórii aj A aj zakázané B, počty sa
        po presune sčítajú, nič sa nestratí."""
        prevadzka = Prevadzka.objects.create(
            celok=Celok.objects.create(nazov="Menu-redirect merge test celok"),
            nazov="Menu-redirect merge test prevádzka",
            visible_menus=["A", "B"],
            menu_day_restrictions={"B": [5]},
        )
        data = {
            "breakfast": {},
            "lunch": {"Dospelý": {"menuCounts": {"A": 1, "B": 2}, "diets": {}}},
            "olovrant": {},
        }
        auto_data = _build_auto_data(
            DailyOrder(data=data, prevadzka=prevadzka),
            visible_meals=[],
            target_date=TUESDAY,
        )
        assert auto_data["lunch"]["Dospelý"]["menuCounts"] == {"A": 3}


@pytest.mark.django_db
class TestApplyAutoOrders:
    """Test apply_auto_orders() service and its business logic."""

    def test_no_orders_created_without_history(self, user):
        """Client with no prior orders → no auto order created."""
        result = apply_auto_orders(target_date=TUESDAY)

        assert user.email not in result["created"]
        assert not DailyOrder.objects.filter(user=user, date=TUESDAY).exists()

    def test_auto_order_created_with_history(self, user):
        """Client with history and no existing order → auto order created."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)

        result = apply_auto_orders(target_date=TUESDAY)

        assert user.email in result["created"]
        auto = DailyOrder.objects.get(user=user, date=TUESDAY)
        assert auto.is_auto is True
        assert auto.status == "submitted"

    def test_closed_day_is_skipped_without_creating_orders(self, user, admin_user):
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)
        ClosedDay.objects.create(date=TUESDAY, closed_by=admin_user)

        result = apply_auto_orders(target_date=TUESDAY)

        assert result == {
            "created": [],
            "skipped": 0,
            "date": TUESDAY.isoformat(),
        }
        assert not DailyOrder.objects.filter(date=TUESDAY).exists()

    def test_open_day_still_creates_auto_order(self, user):
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)

        result = apply_auto_orders(target_date=TUESDAY)

        assert result["created"] == [user.email]
        assert DailyOrder.objects.filter(user=user, date=TUESDAY, is_auto=True).exists()

    def test_manual_order_prevents_auto(self, user):
        """If user already has an order for target_date → no auto order."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)
        DailyOrder.objects.create(user=user, date=TUESDAY, data=EMPTY_DATA)

        result = apply_auto_orders(target_date=TUESDAY)

        assert user.email not in result["created"]
        assert DailyOrder.objects.filter(user=user, date=TUESDAY).count() == 1

    def test_empty_template_does_not_block_future_auto(self, user):
        """Client with explicit empty order in history still gets future auto order."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)
        DailyOrder.objects.create(user=user, date=TUESDAY, data=EMPTY_DATA)

        apply_auto_orders(target_date=WEDNESDAY)

        auto = DailyOrder.objects.filter(user=user, date=WEDNESDAY).first()
        # Respects manual empty order, uses most recent non-empty
        assert auto is not None

    def test_admin_authored_order_still_used_as_auto_order_template(self, admin_user):
        """Objednávka, ktorú namiesto klienta zapísal admin (`DailyOrder.user
        = admin_user`), sa musí preklopiť na ďalší deň rovnako ako klientská.

        Identita riadku je `(prevadzka, date)` — `user` je iba audit toho,
        kto ho naposledy zapísal (viď `DailyOrderViewSet.get_queryset`).
        Predtým `apply_auto_orders` filtroval šablóny cez
        `user_id__in=<klienti>`, takže admin-zapísané objednávky (typicky pri
        prevádzke bez priradeného klientského loginu) sa nikdy nepoužili ako
        šablóna a nikdy sa nepreklopili — nahlásený bug.
        """
        from api.models import Celok, Prevadzka

        celok = Celok.objects.create(nazov="Staff celok")
        prevadzka = Prevadzka.objects.create(celok=celok, nazov="Staff prevádzka")
        DailyOrder.objects.create(
            user=admin_user, date=MONDAY, prevadzka=prevadzka, data=NON_EMPTY_DATA
        )

        result = apply_auto_orders(target_date=TUESDAY)

        assert admin_user.email in result["created"]
        auto = DailyOrder.objects.get(prevadzka=prevadzka, date=TUESDAY)
        assert auto.is_auto is True
        assert auto.data.get("lunch") == NON_EMPTY_DATA["lunch"]

    def test_weekend_target_date_skipped(self, user):
        """Passing a Saturday/Sunday as target_date → service returns early."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)

        result_sat = apply_auto_orders(target_date=SATURDAY)
        result_sun = apply_auto_orders(target_date=SUNDAY)

        assert result_sat["created"] == []
        assert result_sun["created"] == []
        assert not DailyOrder.objects.filter(user=user, date=SATURDAY).exists()
        assert not DailyOrder.objects.filter(user=user, date=SUNDAY).exists()

    def test_visible_meals_respected(self, user):
        """Auto order respects the prevádzka's visible_meals filter."""
        prevadzka = user.profile.dostupne_prevadzky().first()
        prevadzka.visible_meals = ["lunch"]
        prevadzka.save()
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)

        apply_auto_orders(target_date=TUESDAY)

        auto = DailyOrder.objects.get(user=user, date=TUESDAY)
        assert auto.data.get("lunch") == NON_EMPTY_DATA["lunch"]
        # Other meals must be empty
        assert auto.data.get("breakfast") == {}
        assert auto.data.get("olovrant") == {}

    def test_meal_day_restrictions_are_respected(self, user):
        """Raňajky zakázané na cieľový deň — auto-objednávka ich vôbec
        nevytvorí, hoci sú vo visible_meals aj v šablóne (#preklopiť)."""
        prevadzka = user.profile.dostupne_prevadzky().first()
        prevadzka.meal_day_restrictions = {"breakfast": [5]}  # len piatok
        prevadzka.save()
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)

        apply_auto_orders(target_date=TUESDAY)

        auto = DailyOrder.objects.get(user=user, date=TUESDAY)
        assert auto.data.get("breakfast") == {}
        assert auto.data.get("lunch") == NON_EMPTY_DATA["lunch"]

    def test_menu_day_restrictions_redirect_instead_of_dropping(self, user):
        """Menu B len v piatok — v utorok sa počty preklopia do menu A
        namiesto toho, aby sa objednávka jednoducho stratila."""
        prevadzka = user.profile.dostupne_prevadzky().first()
        prevadzka.visible_menus = ["A", "B"]
        prevadzka.menu_day_restrictions = {"B": [5]}
        prevadzka.save()
        DailyOrder.objects.create(
            user=user,
            date=MONDAY,
            data={
                "breakfast": {},
                "lunch": {"Dospelý": {"menuCounts": {"B": 2}, "diets": {}}},
                "olovrant": {},
            },
        )

        apply_auto_orders(target_date=TUESDAY)

        auto = DailyOrder.objects.get(user=user, date=TUESDAY)
        assert auto.data["lunch"]["Dospelý"]["menuCounts"] == {"A": 2}

    def test_apply_auto_orders_carries_pack_separately_forward(self, user):
        prevadzka = user.profile.dostupne_prevadzky().first()
        DailyOrder.objects.create(
            user=user,
            prevadzka=prevadzka,
            date=MONDAY,
            data=NON_EMPTY_DATA_WITH_PACK_SEPARATELY,
        )

        apply_auto_orders(target_date=TUESDAY)

        auto = DailyOrder.objects.get(user=user, prevadzka=prevadzka, date=TUESDAY)
        assert (
            auto.data["lunch"]["Dospelý"]["packSeparately"]
            == NON_EMPTY_DATA_WITH_PACK_SEPARATELY["lunch"]["Dospelý"]["packSeparately"]
        )

    def test_idempotency_no_duplicates(self, user):
        """Running apply_auto_orders twice must not create duplicate orders."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)

        apply_auto_orders(target_date=TUESDAY)
        apply_auto_orders(target_date=TUESDAY)

        assert DailyOrder.objects.filter(user=user, date=TUESDAY).count() == 1

    def test_multiple_clients_independent(self):
        """Each client is processed independently."""
        user1 = _client_user(
            username="user1@example.com",
            email="user1@example.com",
            password="pass123",
        )
        user2 = _client_user(
            username="user2@example.com",
            email="user2@example.com",
            password="pass123",
        )

        # Only user1 has history
        DailyOrder.objects.create(user=user1, date=MONDAY, data=NON_EMPTY_DATA)

        result = apply_auto_orders(target_date=TUESDAY)

        assert user1.email in result["created"]
        assert user2.email not in result["created"]

    def test_return_value_structure(self, user):
        """Result includes 'created' list and match summary."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)

        result = apply_auto_orders(target_date=TUESDAY)

        assert isinstance(result, dict)
        assert "created" in result
        assert isinstance(result["created"], list)
        assert user.email in result["created"]

    def test_filtered_auto_data_is_empty_skipped(self, user):
        """If visible_meals filtering results in empty data → order not created."""
        prevadzka = user.profile.dostupne_prevadzky().get()
        prevadzka.visible_meals = []
        prevadzka.save(update_fields=["visible_meals"])
        DailyOrder.objects.create(user=user, date=MONDAY, data=EMPTY_DATA)

        result = apply_auto_orders(target_date=TUESDAY)

        assert user.email not in result["created"]

    def test_breakfast_source_lunch_applies_end_to_end(self, user):
        """apply_auto_orders naplní raňajky obedom predošlého dňa pre prevádzku
        s `auto_order_breakfast_source='lunch'` (Bystrá scenár)."""
        prevadzka = user.profile.dostupne_prevadzky().first()
        prevadzka.auto_order_breakfast_source = "lunch"
        prevadzka.save(update_fields=["auto_order_breakfast_source"])
        DailyOrder.objects.create(
            user=user, prevadzka=prevadzka, date=MONDAY, data=NON_EMPTY_DATA
        )

        result = apply_auto_orders(target_date=TUESDAY)

        assert user.email in result["created"]
        auto = DailyOrder.objects.get(user=user, prevadzka=prevadzka, date=TUESDAY)
        assert auto.data["breakfast"] == NON_EMPTY_DATA["lunch"]
        assert auto.data["lunch"] == NON_EMPTY_DATA["lunch"]

    def test_paused_prevadzka_gets_no_auto_order_despite_older_history(self, user):
        """`auto_order_paused=True` stops the copy chain even if an older non-empty
        order still exists in history (set directly, bypassing the API layer that
        would normally flip the flag)."""
        prevadzka = user.profile.dostupne_prevadzky().first()
        DailyOrder.objects.create(
            user=user, prevadzka=prevadzka, date=MONDAY, data=NON_EMPTY_DATA
        )
        prevadzka.auto_order_paused = True
        prevadzka.save(update_fields=["auto_order_paused"])

        result = apply_auto_orders(target_date=TUESDAY)

        assert user.email not in result["created"]
        assert not DailyOrder.objects.filter(user=user, date=TUESDAY).exists()

    def test_unpaused_prevadzka_gets_auto_order_again(self, user):
        """Once `auto_order_paused` is cleared, copying resumes from history."""
        prevadzka = user.profile.dostupne_prevadzky().first()
        DailyOrder.objects.create(
            user=user, prevadzka=prevadzka, date=MONDAY, data=NON_EMPTY_DATA
        )
        prevadzka.auto_order_paused = False
        prevadzka.save(update_fields=["auto_order_paused"])

        result = apply_auto_orders(target_date=TUESDAY)

        assert user.email in result["created"]

    def test_edupage_celok_prevadzka_is_skipped_but_app_prevadzka_still_gets_auto(self):
        # Pozor: `on_user_profile_saved` drží `Celok.zdroj_objednavok` v súlade s
        # `is_edupage` profilu, takže EduPage celok tu zámerne nemá vlastný profil —
        # inak by ho signál prepol späť na `app` a test by netestoval pravidlo (a).
        edu_user = _client_user(
            username="edu-celok@example.com",
            email="edu-celok@example.com",
            password="pass123",
        )
        app_user = _client_user(
            username="app-celok@example.com",
            email="app-celok@example.com",
            password="pass123",
        )

        edu_celok = Celok.objects.create(
            nazov="Edu celok auto-order",
            zdroj_objednavok=Celok.ZdrojObjednavok.EDUPAGE,
        )
        edu_prevadzka = Prevadzka.objects.create(celok=edu_celok, nazov="Edu prevadzka")

        app_prevadzka = app_user.profile.dostupne_prevadzky().first()

        DailyOrder.objects.create(
            user=edu_user,
            prevadzka=edu_prevadzka,
            date=MONDAY,
            data=NON_EMPTY_DATA,
        )
        DailyOrder.objects.create(
            user=app_user,
            prevadzka=app_prevadzka,
            date=MONDAY,
            data=NON_EMPTY_DATA,
        )

        result = apply_auto_orders(target_date=TUESDAY)

        assert not DailyOrder.objects.filter(
            prevadzka=edu_prevadzka, date=TUESDAY
        ).exists()
        assert DailyOrder.objects.filter(
            prevadzka=app_prevadzka, date=TUESDAY, is_auto=True
        ).exists()
        assert app_user.email in result["created"]
        assert result["skipped"] >= 1

    def test_app_celok_is_not_skipped_based_on_login_identity(self):
        ordering_user = _client_user(
            username="ordering@example.com",
            email="ordering@example.com",
            password="pass123",
        )
        edupage_user = User.objects.create_user(
            username="edupage-login@example.com",
            email="edupage-login@example.com",
            password="pass123",
        )

        app_celok = Celok.objects.create(
            nazov="Shared app celok",
            zdroj_objednavok=Celok.ZdrojObjednavok.APP,
        )
        shared_prevadzka = Prevadzka.objects.create(
            celok=app_celok, nazov="Shared prevadzka"
        )

        ordering_user.profile.celok_accesses.all().delete()
        ProfileCelokAccess.objects.create(
            profile=ordering_user.profile,
            celok=app_celok,
        )
        edupage_profile = UserProfile(
            user=edupage_user,
            company_name="Shared EduPage login",
        )
        edupage_profile._skip_default_facility = True
        edupage_profile.save()
        ProfilePrevadzkaAccess.objects.create(
            profile=edupage_profile,
            prevadzka=shared_prevadzka,
        )

        DailyOrder.objects.create(
            user=ordering_user,
            prevadzka=shared_prevadzka,
            date=MONDAY,
            data=NON_EMPTY_DATA,
        )

        result = apply_auto_orders(target_date=TUESDAY)

        assert DailyOrder.objects.filter(
            prevadzka=shared_prevadzka, date=TUESDAY
        ).exists()
        assert ordering_user.email in result["created"]


@pytest.mark.django_db
class TestAdminTriggerAutoOrders:
    """Test AdminAutoOrderViewSet POST /api/admin/trigger-auto-orders/ endpoint."""

    def test_admin_can_trigger_auto_orders(self, admin_client, admin_user):
        """Admin can POST to trigger auto-orders."""
        user = _client_user(
            username="client@example.com",
            email="client@example.com",
            password="pass123",
            is_staff=False,
        )
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)

        url = reverse("trigger-auto-orders-list")
        response = admin_client.post(url, {"date": str(TUESDAY)}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert DailyOrder.objects.filter(user=user, date=TUESDAY).exists()

    def test_trigger_endpoint_requires_admin(self, authenticated_client):
        """Non-admin users cannot trigger auto-orders."""
        url = reverse("trigger-auto-orders-list")
        response = authenticated_client.post(url, {"date": str(TUESDAY)}, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_trigger_endpoint_requires_auth(self, api_client):
        """Unauthenticated users cannot trigger auto-orders."""
        url = reverse("trigger-auto-orders-list")
        response = api_client.post(url, {"date": str(TUESDAY)}, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_trigger_without_date_uses_next_workday(self, admin_client, user):
        """Omitting date parameter uses next workday calculation."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)

        url = reverse("trigger-auto-orders-list")
        response = admin_client.post(url, {}, format="json")

        assert response.status_code == status.HTTP_200_OK
        # Verify some order was created (depends on today's date)
        assert response.data.get("created") is not None

    def test_trigger_returns_summary(self, admin_client, user):
        """Trigger endpoint returns summary of created orders."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)

        url = reverse("trigger-auto-orders-list")
        response = admin_client.post(url, {"date": str(TUESDAY)}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert "created" in response.data
        assert "message" in response.data or "skipped" in response.data


@pytest.mark.django_db
class TestAutoOrderTemplateSelection:
    """Test template selection logic in PlannedOrdersViewSet."""

    def test_uses_most_recent_non_empty_as_template(self, authenticated_client, user):
        """Planned orders use most recent non-empty order as template."""
        # Create orders: older empty, newer non-empty
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)
        DailyOrder.objects.create(user=user, date=WEDNESDAY, data=EMPTY_DATA)

        url = reverse("planned-orders-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # Find a workday without existing order; should show predicted data from MONDAY
        for item in response.data:
            if not item["exists"]:
                # Should have predicted data from Monday template
                assert item["predictedTotal"] > 0

    def test_cascade_forward_in_planned_week(self, authenticated_client, user):
        """Planned orders cascade forward orders within the same week."""
        from django.utils import timezone

        today = timezone.localdate()
        import datetime as dt

        # Get first workday
        test_date = today
        while test_date.weekday() >= 5:
            test_date += dt.timedelta(days=1)
        next_date = test_date + dt.timedelta(days=1)
        while next_date.weekday() >= 5:
            next_date += dt.timedelta(days=1)

        # User creates order on first workday
        DailyOrder.objects.create(user=user, date=test_date, data=NON_EMPTY_DATA)

        url = reverse("planned-orders-list")
        response = authenticated_client.get(url)

        # Find items in response
        first_item = next(
            (item for item in response.data if item["date"] == str(test_date)), None
        )
        second_item = next(
            (item for item in response.data if item["date"] == str(next_date)), None
        )

        assert first_item is not None and first_item["exists"]
        assert second_item is None or not second_item["exists"]

    def test_respects_visible_meals_in_predicted(self, authenticated_client, user):
        """Predicted orders should respect visible_meals setting."""
        prevadzka = user.profile.dostupne_prevadzky().get()
        prevadzka.visible_meals = ["lunch"]
        prevadzka.save(update_fields=["visible_meals"])
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)

        url = reverse("planned-orders-list")
        response = authenticated_client.get(url)

        def _sum_ints(value):
            if isinstance(value, int):
                return value
            if isinstance(value, dict):
                return sum(_sum_ints(v) for v in value.values())
            if isinstance(value, (list, tuple)):
                return sum(_sum_ints(v) for v in value)
            return 0

        expected_lunch_total = _sum_ints(NON_EMPTY_DATA.get("lunch", {}))
        found_predicted = False

        # Find a day without order; predicted should only include lunch portions.
        for item in response.data:
            if not item["exists"]:
                found_predicted = True
                assert item["predictedTotal"] == expected_lunch_total

        assert found_predicted

    def test_paused_or_edupage_prevadzka_is_not_shown_as_auto_prediction(
        self, authenticated_client, user
    ):
        """Home predikcia nesmie sľubovať auto-order, ktorý cron preskočí."""
        prevadzka = user.profile.dostupne_prevadzky().get()
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)
        prevadzka.auto_order_paused = True
        prevadzka.save(update_fields=["auto_order_paused"])

        response = authenticated_client.get(reverse("planned-orders-list"))

        assert response.status_code == status.HTTP_200_OK
        assert all(
            item["predictedTotal"] == 0 for item in response.data if not item["exists"]
        )


@pytest.mark.django_db
class TestApplyAutoOrdersScopedTouchedMeals:
    """Regression: Jarabinka /M16 Jasle, 11.9.2026.

    Klient (7.9.) explicitne vynuloval obed na 11.9. (`lunch: {}`), ale
    scoped `apply_auto_orders(meal_types=[...])` beh (raňajky večer vopred,
    obed/olovrant ráno v deň podávania) to o pár hodín neskôr ticho prepísal
    šablónou z predošlého dňa — `_scoped_is_empty` (počet > 0) nevedelo
    odlíšiť "klient zadal 0" od "klient sa k jedlu vôbec nedostal", a zápis
    šiel cez `save(update_fields=["data"])`, teda bez `updated_at` aj bez
    EventLogu. Fix: `DailyOrder.touched_meals` — jedlo raz explicitne
    odkliknuté (aj na nulu) sa už nikdy nepovažuje za "chýbajúce".
    """

    def test_scoped_fill_backfills_untouched_empty_meal_by_default(self, user):
        """Bez `touched_meals` sa prázdne jedlo doplní šablónou — dokumentuje
        zámerné správanie pre rozdelenie raňajky/obed na dva samostatné crony."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)
        existing = DailyOrder.objects.create(user=user, date=TUESDAY, data=EMPTY_DATA)
        assert existing.touched_meals == []

        result = apply_auto_orders(target_date=TUESDAY, meal_types=["lunch"])

        existing.refresh_from_db()
        assert existing.data["lunch"] == NON_EMPTY_DATA["lunch"]
        assert user.email in result["created"]

    def test_touched_meal_is_never_backfilled_even_when_empty(self, user):
        """Presne nahlásený bug: `lunch` je v `touched_meals` (klient ho
        explicitne zadal na 0) — scoped auto-fill ho nesmie prepísať."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)
        existing = DailyOrder.objects.create(
            user=user, date=TUESDAY, data=EMPTY_DATA, touched_meals=["lunch"]
        )

        result = apply_auto_orders(target_date=TUESDAY, meal_types=["lunch"])

        existing.refresh_from_db()
        assert existing.data["lunch"] == EMPTY_DATA["lunch"]
        assert user.email not in result["created"]

    def test_touched_meal_write_is_fully_skipped_no_bump_no_log(self, user):
        """Keď sa nič nedoplní (všetko touched), nesmie sa meniť ani
        `updated_at`, ani pribudnúť EventLog — žiadny zápis sa nekonal."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)
        existing = DailyOrder.objects.create(
            user=user, date=TUESDAY, data=EMPTY_DATA, touched_meals=["lunch"]
        )
        before_updated_at = existing.updated_at
        before_log_count = EventLog.objects.filter(
            prevadzka_id=existing.prevadzka_id
        ).count()

        apply_auto_orders(target_date=TUESDAY, meal_types=["lunch"])

        existing.refresh_from_db()
        assert existing.updated_at == before_updated_at
        assert (
            EventLog.objects.filter(prevadzka_id=existing.prevadzka_id).count()
            == before_log_count
        )

    def test_scoped_fill_reloads_locked_row_before_writing(self, user):
        """Zápis klienta po preloade a pred cron save nesmie byť prepísaný."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)
        existing = DailyOrder.objects.create(user=user, date=TUESDAY, data=EMPTY_DATA)
        original_select_for_update = DailyOrder.objects.select_for_update
        client_write_done = False

        def select_for_update_after_client_write(*args, **kwargs):
            nonlocal client_write_done
            if not client_write_done:
                # Simuluje request, ktorý prešiel validáciou tesne pred
                # uzávierkou a commitne po preloade cronu.
                DailyOrder.objects.filter(pk=existing.pk).update(
                    data=EMPTY_DATA,
                    touched_meals=["lunch"],
                )
                client_write_done = True
            return original_select_for_update(*args, **kwargs)

        with patch.object(
            DailyOrder.objects,
            "select_for_update",
            side_effect=select_for_update_after_client_write,
        ):
            apply_auto_orders(target_date=TUESDAY, meal_types=["lunch"])

        existing.refresh_from_db()
        assert client_write_done
        assert existing.data["lunch"] == {}
        assert existing.touched_meals == ["lunch"]

    def test_scoped_fill_of_untouched_meal_bumps_updated_at_and_logs_event(self, user):
        """Keď sa scoped beh naozaj dotkne netknutého jedla, musí to teraz
        byť vidno — predtým `save(update_fields=["data"])` obišlo aj
        `updated_at`, aj EventLog úplne potichu."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)
        existing = DailyOrder.objects.create(user=user, date=TUESDAY, data=EMPTY_DATA)
        before_updated_at = existing.updated_at

        apply_auto_orders(target_date=TUESDAY, meal_types=["lunch"])

        existing.refresh_from_db()
        assert existing.updated_at > before_updated_at
        event = EventLog.objects.filter(
            prevadzka_id=existing.prevadzka_id,
            event_type=EventLog.EventType.ORDER_ADMIN_UPDATE,
        ).latest("created_at")
        assert event.payload["filled_meals"] == ["lunch"]
        assert event.payload["date"] == TUESDAY.isoformat()

    def test_partially_touched_row_only_fills_untouched_meals(self, user):
        """`lunch` touched (chránené), `olovrant` netknuté (doplní sa, ak má
        šablóna obsah) — v tom istom riadku, v tom istom behu."""
        template_data = {
            "breakfast": {"Dospelý": {"menuCounts": {"A": 1}, "diets": {}}},
            "lunch": {"Dospelý": {"menuCounts": {"B": 2}, "diets": {}}},
            "olovrant": {"Dospelý": {"menuCounts": {"A": 1}, "diets": {}}},
        }
        DailyOrder.objects.create(user=user, date=MONDAY, data=template_data)
        existing = DailyOrder.objects.create(
            user=user,
            date=TUESDAY,
            data={"breakfast": {}, "lunch": {}, "olovrant": {}},
            touched_meals=["lunch"],
        )

        apply_auto_orders(target_date=TUESDAY, meal_types=["lunch", "olovrant"])

        existing.refresh_from_db()
        assert existing.data["lunch"] == {}
        assert existing.data["olovrant"] == template_data["olovrant"]

    def test_touched_meals_defaults_to_empty_list(self, user):
        """Nové pole na historických/nových riadkoch defaultuje na `[]` —
        spätne kompatibilné, žiadna migrácia dát netreba."""
        existing = DailyOrder.objects.create(user=user, date=TUESDAY, data=EMPTY_DATA)
        assert existing.touched_meals == []

    def test_scoped_new_order_is_audited(self, user):
        """Aj vytvorenie nového scoped auto-riadka musí mať per-order audit."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)

        apply_auto_orders(target_date=TUESDAY, meal_types=["lunch"])

        order = DailyOrder.objects.get(user=user, date=TUESDAY)
        event = EventLog.objects.get(
            event_type=EventLog.EventType.ORDER_ADMIN_UPDATE,
            payload__order_id=order.pk,
        )
        assert event.payload["filled_meals"] == ["lunch"]


@pytest.mark.django_db
class TestAutoOrderEdgeCases:
    """Test edge cases and corner scenarios."""

    def test_empty_dict_data_handled(self, user):
        """Orders with empty data dict are handled correctly."""
        order = DailyOrder.objects.create(user=user, date=MONDAY, data={})

        result = _is_order_empty(order.data or {})
        assert result is True

    def test_missing_menuCounts_key(self, user):
        """Orders with missing menuCounts key are handled."""
        data = {"breakfast": {"Dospelý": {"diets": {}}}}

        result = _is_order_empty(data)
        assert result is True

    def test_many_clients_performance(self, db):
        """Service handles many clients efficiently."""
        # Create 10 clients with history
        clients = [
            _client_user(
                username=f"client{i}@example.com",
                email=f"client{i}@example.com",
                password="pass123",
            )
            for i in range(10)
        ]

        for client in clients:
            DailyOrder.objects.create(user=client, date=MONDAY, data=NON_EMPTY_DATA)

        result = apply_auto_orders(target_date=TUESDAY)

        assert len(result["created"]) == 10

    def test_various_visible_meals_combinations(self, user):
        """Test all combinations of visible_meals."""
        prevadzka = user.profile.dostupne_prevadzky().first()
        for combo in [
            ["breakfast"],
            ["lunch"],
            ["olovrant"],
            ["breakfast", "lunch"],
            ["breakfast", "olovrant"],
            ["lunch", "olovrant"],
            ["breakfast", "lunch", "olovrant"],
        ]:
            prevadzka.visible_meals = combo
            prevadzka.save()
            DailyOrder.objects.filter(user=user).delete()
            DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)

            result = apply_auto_orders(target_date=TUESDAY)

            if result["created"]:
                auto = DailyOrder.objects.get(user=user, date=TUESDAY)
                # Verify only allowed meals have data
                for meal in ["breakfast", "lunch", "olovrant"]:
                    if meal in combo:
                        template_meal_data = NON_EMPTY_DATA.get(meal, {})
                        assert auto.data.get(meal, {}) == template_meal_data
                    else:
                        assert auto.data.get(meal) == {}


@pytest.mark.django_db
class TestAutoOrderTimezone:
    """
    Regression test for H2: apply_auto_orders must use the local (Europe/Bratislava)
    date, not UTC.  At 23:30 local time (UTC+1) UTC is already on the next calendar
    day, so a UTC-based `today` would skip ahead by one workday.
    """

    def test_localdate_used_near_local_midnight(self, user):
        """
        Mock timezone.localdate() to return MONDAY (simulating 23:30 local on Mon).
        The service should target TUESDAY.  A UTC-based implementation seeing "today
        is Tuesday" would instead target WEDNESDAY — this test catches the regression.
        """
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)

        with patch(
            "api.services.auto_order_service.timezone.localdate", return_value=MONDAY
        ):
            result = apply_auto_orders()

        # Auto-order should have been created for TUESDAY (next workday after MONDAY)
        created_order = DailyOrder.objects.filter(
            user=user, date=TUESDAY, is_auto=True
        ).first()
        assert (
            created_order is not None
        ), f"Expected auto-order on TUESDAY but none was created. Result: {result}"
