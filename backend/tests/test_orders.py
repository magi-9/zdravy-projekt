from datetime import date, datetime, time, timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from api.models import DailyOrder, GlobalSettings, PortionType

# Constants mimicking frontend
CATEGORIES = ["Jasle", "Škôlka", "ZŠ 1.stupeň", "ZŠ 2.stupeň", "Dospelý (SŠ)"]
DIETS = ["Bez lepku", "Bez laktózy", "Vegetariánske", "Vegánske", "Diabetické"]
FUTURE_ORDER_DATE = date(2099, 1, 2)


@pytest.mark.django_db
class TestOrderPermissions:
    def test_list_orders_authenticated(self, authenticated_client):
        """Authenticated user can list orders"""
        url = reverse("dailyorder-list")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_list_orders_unauthenticated(self, api_client):
        """Unauthenticated user cannot list orders"""
        url = reverse("dailyorder-list")
        response = api_client.get(url)
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_user_isolation(self, authenticated_client, api_client, user, other_user):
        """User cannot see other user's orders"""
        from api.models import UserProfile

        # other_user má profil → jednoznačná prevádzka, kam objednávku doplniť
        UserProfile.objects.get_or_create(
            user=other_user, defaults={"company_name": other_user.email}
        )
        # Create order for other user
        DailyOrder.objects.create(
            user=other_user, date=date.today(), data={"lunch": {"menuCounts": {"A": 1}}}
        )

        # User checks their list
        url = reverse("dailyorder-list")
        response = authenticated_client.get(url)

        # User should see 0 orders (or only their own)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data.get("results", response.data)) == 0

    def test_admin_restriction(self, authenticated_client, user):
        """Admin/Staff user cannot create orders"""
        user.is_staff = True
        user.save()

        url = reverse("dailyorder-list")
        today = date.today()
        payload = {
            "date": str(today),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"A": 1}}},
        }
        response = authenticated_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestOrderCRUD:
    def test_create_order_simple(self, authenticated_client, user):
        """Test simple order creation"""
        url = reverse("dailyorder-list")
        today = FUTURE_ORDER_DATE
        payload = {
            "date": str(today),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"A": 1}, "diets": {}}},
        }
        response = authenticated_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        # Verify DB
        order = DailyOrder.objects.get(user=user, date=today)
        assert order.data["lunch"]["menuCounts"]["A"] == 1
        assert order.status == "submitted"

    def test_update_order_idempotency(self, authenticated_client, user):
        """Test that posting again updates the existing order (idempotency/upsert)"""
        today = FUTURE_ORDER_DATE
        # Initial
        DailyOrder.objects.create(
            user=user,
            date=today,
            status="draft",
            data={"lunch": {"menuCounts": {"A": 1}}},
        )

        url = reverse("dailyorder-list")
        payload = {
            "date": str(today),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"A": 2}, "diets": {}}},  # Changed 1 -> 2
        }

        response = authenticated_client.post(url, payload, format="json")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_201_CREATED,
        ]

        # Verify Update
        order = DailyOrder.objects.get(user=user, date=today)
        assert order.data["lunch"]["menuCounts"]["A"] == 2
        assert order.status == "submitted"
        # Ensure no duplicates
        assert DailyOrder.objects.filter(user=user, date=today).count() == 1

    def test_full_frontend_payload(self, authenticated_client, user):
        """Test saving a complex payload similar to what frontend sends"""
        today = FUTURE_ORDER_DATE
        url = reverse("dailyorder-list")

        # Construct a complex nested structure
        data = {"breakfast": {}, "lunch": {}, "olovrant": {}}

        for cat in CATEGORIES:
            data["lunch"][cat] = {
                "menuCounts": {"A": 5, "B": 2},
                "diets": {d: 1 for d in DIETS},
            }

        payload = {"date": str(today), "status": "submitted", "data": data}

        response = authenticated_client.post(url, payload, format="json")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_201_CREATED,
        ]

        order = DailyOrder.objects.get(user=user, date=today)
        saved_data = order.data
        assert saved_data["lunch"]["Jasle"]["menuCounts"]["A"] == 5
        assert saved_data["lunch"]["Jasle"]["diets"]["Bez lepku"] == 1

    def test_delete_logic_frontend_style(self, authenticated_client, user):
        """Test 'soft delete' logic as used by frontend
        (setting status to draft and empty data)"""
        today = FUTURE_ORDER_DATE
        # Create existing order
        DailyOrder.objects.create(
            user=user,
            date=today,
            status="submitted",
            data={"lunch": {"menuCounts": {"A": 10}}},
        )

        url = reverse("dailyorder-list")
        # Frontend 'deletes' by setting status to draft and reset data
        empty_meal = {}
        # In reality frontend sends a deep structure of zeroes,
        # but empty dict should be valid too
        payload = {
            "date": str(today),
            "status": "draft",
            "data": {
                "breakfast": empty_meal,
                "lunch": empty_meal,
                "olovrant": empty_meal,
            },
        }
        response = authenticated_client.post(url, payload, format="json")
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]

        # Verify DB is empty (drafts not persisted)
        assert not DailyOrder.objects.filter(user=user, date=today).exists()

    def test_by_date_endpoint(self, authenticated_client, user):
        """Test retrieving order by date"""
        today = date.today()
        DailyOrder.objects.create(
            user=user,
            date=today,
            status="submitted",
            data={"lunch": {"menuCounts": {"A": 3}}},
        )

        url = reverse("dailyorder-by-date", kwargs={"date": str(today)})
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["lunch"]["menuCounts"]["A"] == 3

    def test_by_date_not_found(self, authenticated_client):
        """Test retrieving non-existent order returns empty data
        instead of 404 (as per view logic)"""
        # Note: The view returns 200 with empty data structure if not found
        tomorrow = date(2099, 1, 1)
        url = reverse("dailyorder-by-date", kwargs={"date": str(tomorrow)})
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"data": {}}

    def test_monthly_summary_counts_user_orders(
        self, authenticated_client, user, other_user
    ):
        from api.models import UserProfile

        UserProfile.objects.get_or_create(
            user=other_user, defaults={"company_name": other_user.email}
        )
        DailyOrder.objects.create(
            user=user,
            date=date(2099, 1, 2),
            status="submitted",
            data={
                "breakfast": {"Škôlka": {"menuCounts": {"A": 2}, "diets": {}}},
                "lunch": {"Škôlka": {"menuCounts": {"A": 3, "B": 1}, "diets": {}}},
                "olovrant": {},
            },
        )
        DailyOrder.objects.create(
            user=user,
            date=date(2099, 1, 3),
            status="draft",
            data={"lunch": {"Škôlka": {"menuCounts": {"A": 99}, "diets": {}}}},
        )
        DailyOrder.objects.create(
            user=other_user,
            date=date(2099, 1, 2),
            status="submitted",
            data={"lunch": {"Škôlka": {"menuCounts": {"A": 99}, "diets": {}}}},
        )

        response = authenticated_client.get(
            "/api/orders/planned/monthly-summary/?year=2099&month=1"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["total"] == 105
        assert response.data["menu_counts"] == {"A": 104, "B": 1}
        assert response.data["meal_counts"]["breakfast"] == 2
        assert response.data["meal_counts"]["lunch"] == 103

    def test_portion_types_list_is_available_to_clients(self, authenticated_client):
        PortionType.objects.create(
            name="Škôlka", coefficient="1.0000", sort_order=1, is_active=True
        )
        PortionType.objects.create(
            name="Interná", coefficient="2.0000", sort_order=2, is_active=False
        )

        response = authenticated_client.get("/api/admin/portion-types/")

        assert response.status_code == status.HTTP_200_OK
        data = response.data
        results = data["results"] if isinstance(data, dict) else data
        names = [item["name"] for item in results]
        assert names == ["Škôlka"]


@pytest.mark.django_db
class TestOrderDeadlines:
    @staticmethod
    def _server_dt(year: int, month: int, day: int, hour: int, minute: int):
        return timezone.make_aware(
            datetime(year, month, day, hour, minute),
            timezone.get_current_timezone(),
        )

    @staticmethod
    def _set_global_deadlines(**overrides):
        defaults = {
            "deadline_breakfast": time(8, 0),
            "deadline_breakfast_is_day_before": False,
            "deadline_lunch": time(10, 0),
            "deadline_lunch_is_day_before": False,
            "deadline_olovrant": time(14, 0),
            "deadline_olovrant_is_day_before": False,
        }
        defaults.update(overrides)
        GlobalSettings.objects.update_or_create(pk=1, defaults=defaults)

    def test_create_order_after_today_deadline_is_rejected(
        self, authenticated_client, user
    ):
        self._set_global_deadlines(deadline_lunch=time(10, 0))
        today = date(2026, 3, 13)
        payload = {
            "date": str(today),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"A": 1}, "diets": {}}},
        }

        with patch(
            "api.serializers.timezone.localtime",
            return_value=self._server_dt(2026, 3, 13, 10, 1),
        ):
            response = authenticated_client.post(
                reverse("dailyorder-list"), payload, format="json"
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "order_deadline_passed"
        assert DailyOrder.objects.filter(user=user, date=today).count() == 0

    def test_deadline_rejection_is_logged_with_which_meal_and_who(
        self, authenticated_client, user
    ):
        """Predtým sa zamietnutie nikde nezapísalo — dohľadať, PREČO konkrétny
        request padol, šlo len ručnou rekonštrukciou nad produkčnou DB
        (incident Vyšehradská, 2.9.2026). Log musí niesť aspoň e-mail
        používateľa a detail chyby (ktoré jedlo, aký termín)."""
        self._set_global_deadlines(deadline_lunch=time(10, 0))
        today = date(2026, 3, 13)
        payload = {
            "date": str(today),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"A": 1}, "diets": {}}},
        }

        with patch(
            "api.serializers.timezone.localtime",
            return_value=self._server_dt(2026, 3, 13, 10, 1),
        ), patch("api.exception_handlers.logger.warning") as mock_warning:
            response = authenticated_client.post(
                reverse("dailyorder-list"), payload, format="json"
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        mock_warning.assert_called_once()
        logged = mock_warning.call_args.args
        assert "order_deadline_passed" in logged
        assert user.email in logged
        assert any("obed" in str(arg).lower() for arg in logged)

    def test_deadline_error_has_frontend_contract_shape(self, authenticated_client):
        self._set_global_deadlines(deadline_lunch=time(10, 0))
        today = date(2026, 3, 13)
        payload = {
            "date": str(today),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"A": 1}, "diets": {}}},
        }

        with patch(
            "api.serializers.timezone.localtime",
            return_value=self._server_dt(2026, 3, 13, 10, 1),
        ):
            response = authenticated_client.post(
                reverse("dailyorder-list"), payload, format="json"
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.data
        assert response.data["error"]["code"] == "order_deadline_passed"
        assert "message" in response.data["error"]
        assert isinstance(response.data["error"]["message"], str)
        assert "details" in response.data["error"]
        assert response.data["error"]["details"]["deadline"] == "13.03.2026 10:00"
        assert response.data["error"]["details"]["current_time"] == "13.03.2026 10:01"

    def test_upsert_existing_order_after_deadline_is_rejected(
        self, authenticated_client, user
    ):
        self._set_global_deadlines(deadline_lunch=time(10, 0))
        today = date(2026, 3, 13)
        DailyOrder.objects.create(
            user=user,
            date=today,
            status="submitted",
            data={"lunch": {"menuCounts": {"A": 1}, "diets": {}}},
        )
        payload = {
            "date": str(today),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"A": 2}, "diets": {}}},
        }

        with patch(
            "api.serializers.timezone.localtime",
            return_value=self._server_dt(2026, 3, 13, 10, 5),
        ):
            response = authenticated_client.post(
                reverse("dailyorder-list"), payload, format="json"
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert (
            DailyOrder.objects.get(user=user, date=today).data["lunch"]["menuCounts"][
                "A"
            ]
            == 1
        )

    def test_patch_existing_order_after_deadline_is_rejected(
        self, authenticated_client, user
    ):
        self._set_global_deadlines(deadline_lunch=time(10, 0))
        today = date(2026, 3, 13)
        order = DailyOrder.objects.create(
            user=user,
            date=today,
            status="submitted",
            data={"lunch": {"menuCounts": {"A": 1}, "diets": {}}},
        )

        with patch(
            "api.serializers.timezone.localtime",
            return_value=self._server_dt(2026, 3, 13, 10, 10),
        ):
            response = authenticated_client.patch(
                reverse("dailyorder-detail", args=[order.id]),
                {"data": {"lunch": {"menuCounts": {"A": 3}, "diets": {}}}},
                format="json",
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        order.refresh_from_db()
        assert order.data["lunch"]["menuCounts"]["A"] == 1

    def test_day_before_deadline_comes_from_global_settings(
        self, authenticated_client, user
    ):
        self._set_global_deadlines(
            deadline_lunch=time(9, 30),
            deadline_lunch_is_day_before=True,
        )
        friday = date(2026, 3, 13)
        payload = {
            "date": str(friday),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"A": 1}, "diets": {}}},
        }

        with patch(
            "api.serializers.timezone.localtime",
            return_value=self._server_dt(2026, 3, 12, 9, 31),
        ):
            response = authenticated_client.post(
                reverse("dailyorder-list"), payload, format="json"
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert DailyOrder.objects.filter(user=user, date=friday).count() == 0

    def test_reshaped_but_unchanged_locked_meal_does_not_block_other_meals(
        self, authenticated_client, user
    ):
        """Regression for a real incident: breakfast deadline is 21:00 the day
        before, lunch deadline is same-day 07:30. The frontend re-normalizes
        every meal it resubmits (fills in zero-count keys the current schema
        knows about, even ones absent from the originally stored JSON). That
        reshaping must not make an untouched, already-locked breakfast look
        "changed" and block a still-open lunch edit.
        """
        self._set_global_deadlines(
            deadline_breakfast=time(21, 0),
            deadline_breakfast_is_day_before=True,
            deadline_lunch=time(7, 30),
            deadline_lunch_is_day_before=False,
        )
        today = date(2026, 3, 13)
        DailyOrder.objects.create(
            user=user,
            date=today,
            status="submitted",
            data={
                "breakfast": {"menuCounts": {"A": 3}, "diets": {}},
                "lunch": {"menuCounts": {"A": 1}, "diets": {}},
            },
        )
        payload = {
            "date": str(today),
            "status": "submitted",
            "data": {
                # Same content as stored, but reshaped: extra zero-count keys
                # the frontend's schema normalization would add.
                "breakfast": {
                    "menuCounts": {"A": 3, "B": 0},
                    "diets": {"Bez lepku": 0},
                },
                "lunch": {"menuCounts": {"A": 2}, "diets": {}},
            },
        }

        with patch(
            "api.serializers.timezone.localtime",
            return_value=self._server_dt(2026, 3, 13, 7, 20),
        ):
            response = authenticated_client.post(
                reverse("dailyorder-list"), payload, format="json"
            )

        assert response.status_code == status.HTTP_201_CREATED
        order = DailyOrder.objects.get(user=user, date=today)
        assert order.data["lunch"]["menuCounts"]["A"] == 2
        assert order.data["breakfast"]["menuCounts"]["A"] == 3

    def test_genuinely_changed_locked_meal_is_still_rejected(
        self, authenticated_client, user
    ):
        self._set_global_deadlines(
            deadline_breakfast=time(21, 0),
            deadline_breakfast_is_day_before=True,
            deadline_lunch=time(7, 30),
            deadline_lunch_is_day_before=False,
        )
        today = date(2026, 3, 13)
        DailyOrder.objects.create(
            user=user,
            date=today,
            status="submitted",
            data={
                "breakfast": {"menuCounts": {"A": 3}, "diets": {}},
                "lunch": {"menuCounts": {"A": 1}, "diets": {}},
            },
        )
        payload = {
            "date": str(today),
            "status": "submitted",
            "data": {
                # Genuine content change to the locked meal.
                "breakfast": {"menuCounts": {"A": 5}, "diets": {}},
                "lunch": {"menuCounts": {"A": 2}, "diets": {}},
            },
        }

        with patch(
            "api.serializers.timezone.localtime",
            return_value=self._server_dt(2026, 3, 13, 7, 20),
        ):
            response = authenticated_client.post(
                reverse("dailyorder-list"), payload, format="json"
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        order = DailyOrder.objects.get(user=user, date=today)
        assert order.data["breakfast"]["menuCounts"]["A"] == 3
        assert order.data["lunch"]["menuCounts"]["A"] == 1

    def test_menu_bc_order_after_own_deadline_is_rejected(
        self, authenticated_client, user
    ):
        """Menu B/C have a stricter deadline (e.g. 7:30, 2 days before) that
        applies independently of the meal's own deadline."""
        self._set_global_deadlines(
            deadline_lunch=time(23, 0),
            deadline_menu_bc=time(7, 30),
            deadline_menu_bc_days_before=2,
        )
        target_date = date(2026, 3, 13)  # Friday
        payload = {
            "date": str(target_date),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"B": 1}, "diets": {}}},
        }

        # Deadline is Wed 2026-03-11 07:30; just past it.
        with patch(
            "api.serializers.timezone.localtime",
            return_value=self._server_dt(2026, 3, 11, 7, 31),
        ):
            response = authenticated_client.post(
                reverse("dailyorder-list"), payload, format="json"
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert DailyOrder.objects.filter(user=user, date=target_date).count() == 0

    def test_menu_d_order_after_own_deadline_is_rejected(
        self, authenticated_client, user
    ):
        """Menu D zdieľa rovnaký prísnejší termín ako B/C."""
        self._set_global_deadlines(
            deadline_lunch=time(23, 0),
            deadline_menu_bc=time(7, 30),
            deadline_menu_bc_days_before=2,
        )
        target_date = date(2026, 3, 13)  # Friday
        payload = {
            "date": str(target_date),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"D": 1}, "diets": {}}},
        }

        with patch(
            "api.serializers.timezone.localtime",
            return_value=self._server_dt(2026, 3, 11, 7, 31),
        ):
            response = authenticated_client.post(
                reverse("dailyorder-list"), payload, format="json"
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert DailyOrder.objects.filter(user=user, date=target_date).count() == 0

    def test_menu_bc_order_before_own_deadline_is_allowed(
        self, authenticated_client, user
    ):
        self._set_global_deadlines(
            deadline_lunch=time(23, 0),
            deadline_menu_bc=time(7, 30),
            deadline_menu_bc_days_before=2,
        )
        target_date = date(2026, 3, 13)
        payload = {
            "date": str(target_date),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"C": 1}, "diets": {}}},
        }

        # Still before Wed 2026-03-11 07:30.
        with patch(
            "api.serializers.timezone.localtime",
            return_value=self._server_dt(2026, 3, 11, 7, 29),
        ):
            response = authenticated_client.post(
                reverse("dailyorder-list"), payload, format="json"
            )

        assert response.status_code == status.HTTP_201_CREATED
        assert (
            DailyOrder.objects.get(user=user, date=target_date).data["lunch"][
                "menuCounts"
            ]["C"]
            == 1
        )

    def test_menu_a_order_still_allowed_after_bc_deadline(
        self, authenticated_client, user
    ):
        """The B/C-specific deadline must not block menu A, which only obeys
        the regular per-meal deadline."""
        self._set_global_deadlines(
            deadline_lunch=time(23, 0),
            deadline_menu_bc=time(7, 30),
            deadline_menu_bc_days_before=2,
        )
        target_date = date(2026, 3, 13)
        payload = {
            "date": str(target_date),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"A": 1}, "diets": {}}},
        }

        with patch(
            "api.serializers.timezone.localtime",
            return_value=self._server_dt(2026, 3, 11, 7, 31),
        ):
            response = authenticated_client.post(
                reverse("dailyorder-list"), payload, format="json"
            )

        assert response.status_code == status.HTTP_201_CREATED

    def test_menu_bc_change_on_existing_order_after_deadline_is_rejected(
        self, authenticated_client, user
    ):
        self._set_global_deadlines(
            deadline_lunch=time(23, 0),
            deadline_menu_bc=time(7, 30),
            deadline_menu_bc_days_before=2,
        )
        target_date = date(2026, 3, 13)
        DailyOrder.objects.create(
            user=user,
            date=target_date,
            status="submitted",
            data={"lunch": {"menuCounts": {"A": 1, "B": 1}, "diets": {}}},
        )
        payload = {
            "date": str(target_date),
            "status": "submitted",
            # Menu A count unchanged; only the restricted menu B changes.
            "data": {"lunch": {"menuCounts": {"A": 1, "B": 2}, "diets": {}}},
        }

        with patch(
            "api.serializers.timezone.localtime",
            return_value=self._server_dt(2026, 3, 11, 7, 31),
        ):
            response = authenticated_client.post(
                reverse("dailyorder-list"), payload, format="json"
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        order = DailyOrder.objects.get(user=user, date=target_date)
        assert order.data["lunch"]["menuCounts"]["B"] == 1

    def test_menu_bc_decrease_after_strict_deadline_but_before_morning_is_allowed(
        self, authenticated_client, user
    ):
        """User 2.9.2026: odhlásiť/znížiť Menu B/C sa dá až do rána v deň
        výdaja, aj keď prísny 2-dňový termín na NOVÉ/vyššie objednávky už
        prešiel — inak by rodič nemohol dieťa odhlásiť tesne pred obedom."""
        self._set_global_deadlines(
            deadline_lunch=time(23, 0),
            deadline_menu_bc=time(7, 30),
            deadline_menu_bc_days_before=2,
        )
        target_date = date(2026, 3, 13)  # Friday
        DailyOrder.objects.create(
            user=user,
            date=target_date,
            status="submitted",
            data={"lunch": {"menuCounts": {"A": 1, "B": 2}, "diets": {}}},
        )
        payload = {
            "date": str(target_date),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"A": 1, "B": 1}, "diets": {}}},
        }

        # Strict 2-day deadline (Wed 07:30) is long past, but it's still
        # before Friday 07:30 (the meal's own day) — a decrease must go through.
        with patch(
            "api.serializers.timezone.localtime",
            return_value=self._server_dt(2026, 3, 13, 7, 0),
        ):
            response = authenticated_client.post(
                reverse("dailyorder-list"), payload, format="json"
            )

        assert response.status_code == status.HTTP_201_CREATED
        order = DailyOrder.objects.get(user=user, date=target_date)
        assert order.data["lunch"]["menuCounts"]["B"] == 1

    def test_menu_bc_decrease_after_meal_day_morning_is_rejected(
        self, authenticated_client, user
    ):
        """Odhlásenie má vlastný termín (rovnaký čas, deň výdaja) — nie je to
        neobmedzené donekonečna, len dlhšie než nahlásenie."""
        self._set_global_deadlines(
            deadline_lunch=time(23, 0),
            deadline_menu_bc=time(7, 30),
            deadline_menu_bc_days_before=2,
        )
        target_date = date(2026, 3, 13)  # Friday
        DailyOrder.objects.create(
            user=user,
            date=target_date,
            status="submitted",
            data={"lunch": {"menuCounts": {"A": 1, "B": 2}, "diets": {}}},
        )
        payload = {
            "date": str(target_date),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"A": 1, "B": 1}, "diets": {}}},
        }

        with patch(
            "api.serializers.timezone.localtime",
            return_value=self._server_dt(2026, 3, 13, 7, 31),
        ):
            response = authenticated_client.post(
                reverse("dailyorder-list"), payload, format="json"
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        order = DailyOrder.objects.get(user=user, date=target_date)
        assert order.data["lunch"]["menuCounts"]["B"] == 2

    def test_menu_bc_full_cancellation_after_strict_deadline_is_allowed(
        self, authenticated_client, user
    ):
        """Odhlásenie na nulu (menu úplne zmizne z payloadu) je tiež pokles,
        nie nárast — musí prejsť rovnako ako čiastočné zníženie."""
        self._set_global_deadlines(
            deadline_lunch=time(23, 0),
            deadline_menu_bc=time(7, 30),
            deadline_menu_bc_days_before=2,
        )
        target_date = date(2026, 3, 13)
        DailyOrder.objects.create(
            user=user,
            date=target_date,
            status="submitted",
            data={"lunch": {"menuCounts": {"A": 1, "B": 2}, "diets": {}}},
        )
        payload = {
            "date": str(target_date),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"A": 1}, "diets": {}}},
        }

        with patch(
            "api.serializers.timezone.localtime",
            return_value=self._server_dt(2026, 3, 13, 7, 0),
        ):
            response = authenticated_client.post(
                reverse("dailyorder-list"), payload, format="json"
            )

        assert response.status_code == status.HTTP_201_CREATED
        order = DailyOrder.objects.get(user=user, date=target_date)
        assert "B" not in order.data["lunch"]["menuCounts"]

    def test_menu_bc_order_after_own_deadline_is_allowed_when_prevadzka_exempt(
        self, authenticated_client, user
    ):
        """`menu_bc_same_deadline_as_lunch` (user 10.9.2026: piatkové Menu B
        pre deti bez narýchlo dokupovania) — prísny 2-dňový termín sa na túto
        prevádzku vôbec nevzťahuje, platí len bežná uzávierka obeda."""
        prevadzka = user.profile.dostupne_prevadzky().first()
        prevadzka.menu_bc_same_deadline_as_lunch = True
        prevadzka.save(update_fields=["menu_bc_same_deadline_as_lunch"])
        self._set_global_deadlines(
            deadline_lunch=time(23, 0),
            deadline_menu_bc=time(7, 30),
            deadline_menu_bc_days_before=2,
        )
        target_date = date(2026, 3, 13)  # Friday
        payload = {
            "date": str(target_date),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"B": 1}, "diets": {}}},
        }

        # Past the strict 2-day B/C deadline (Wed 07:30), but well before the
        # meal's own deadline (Fri 23:00) — must go through for an exempt
        # prevádzka.
        with patch(
            "api.serializers.timezone.localtime",
            return_value=self._server_dt(2026, 3, 11, 7, 31),
        ):
            response = authenticated_client.post(
                reverse("dailyorder-list"), payload, format="json"
            )

        assert response.status_code == status.HTTP_201_CREATED
        order = DailyOrder.objects.get(user=user, date=target_date)
        assert order.data["lunch"]["menuCounts"]["B"] == 1

    def test_menu_bc_order_still_blocked_by_own_meal_deadline_when_exempt(
        self, authenticated_client, user
    ):
        """Exemption only drops the EXTRA B/C rule — the normal per-meal
        deadline still applies."""
        prevadzka = user.profile.dostupne_prevadzky().first()
        prevadzka.menu_bc_same_deadline_as_lunch = True
        prevadzka.save(update_fields=["menu_bc_same_deadline_as_lunch"])
        self._set_global_deadlines(
            deadline_lunch=time(7, 30),
            deadline_menu_bc=time(7, 30),
            deadline_menu_bc_days_before=2,
        )
        target_date = date(2026, 3, 13)  # Friday
        payload = {
            "date": str(target_date),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"B": 1}, "diets": {}}},
        }

        # Past even the meal's own deadline (Fri 07:30).
        with patch(
            "api.serializers.timezone.localtime",
            return_value=self._server_dt(2026, 3, 13, 7, 31),
        ):
            response = authenticated_client.post(
                reverse("dailyorder-list"), payload, format="json"
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert DailyOrder.objects.filter(user=user, date=target_date).count() == 0

    def test_admin_bypasses_menu_bc_deadline(self, admin_authenticated_client, user):
        prevadzka = user.profile.dostupne_prevadzky().first()
        self._set_global_deadlines(
            deadline_lunch=time(23, 0),
            deadline_menu_bc=time(7, 30),
            deadline_menu_bc_days_before=2,
        )
        target_date = date(2026, 3, 13)
        payload = {
            "date": str(target_date),
            "status": "submitted",
            "prevadzka": prevadzka.id,
            "data": {"lunch": {"menuCounts": {"B": 1}, "diets": {}}},
        }

        with patch(
            "api.serializers.timezone.localtime",
            return_value=self._server_dt(2026, 3, 11, 7, 31),
        ):
            response = admin_authenticated_client.post(
                reverse("dailyorder-list"), payload, format="json"
            )

        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
class TestAutoOrderPauseOnReset:
    """Vynulovanie/zmazanie objednávky trvalo zastaví preklápanie dopredu.

    `apply_auto_orders` kopíruje poslednú NEPRÁZDNU objednávku ako šablónu —
    tieto testy overujú, že `Prevadzka.auto_order_paused` sa nastavuje/ruší
    presne tak, ako to zo serializera volá `_sync_auto_order_pause`.
    """

    def test_submitting_zero_order_pauses_prevadzka(self, authenticated_client, user):
        prevadzka = user.profile.dostupne_prevadzky().first()
        assert prevadzka.auto_order_paused is False

        payload = {
            "date": str(FUTURE_ORDER_DATE),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"A": 0}, "diets": {}}},
        }
        response = authenticated_client.post(
            reverse("dailyorder-list"), payload, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        prevadzka.refresh_from_db()
        assert prevadzka.auto_order_paused is True

    def test_draft_delete_pauses_prevadzka(self, authenticated_client, user):
        prevadzka = user.profile.dostupne_prevadzky().first()
        DailyOrder.objects.create(
            user=user,
            prevadzka=prevadzka,
            date=FUTURE_ORDER_DATE,
            status="submitted",
            data={"lunch": {"menuCounts": {"A": 2}, "diets": {}}},
        )

        payload = {
            "date": str(FUTURE_ORDER_DATE),
            "status": "draft",
            "data": {},
        }
        response = authenticated_client.post(
            reverse("dailyorder-list"), payload, format="json"
        )

        assert response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]
        prevadzka.refresh_from_db()
        assert prevadzka.auto_order_paused is True
        assert not DailyOrder.objects.filter(
            prevadzka=prevadzka, date=FUTURE_ORDER_DATE
        ).exists()

    def test_real_order_unpauses_prevadzka(self, authenticated_client, user):
        prevadzka = user.profile.dostupne_prevadzky().first()
        prevadzka.auto_order_paused = True
        prevadzka.save(update_fields=["auto_order_paused"])

        payload = {
            "date": str(FUTURE_ORDER_DATE),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"A": 3}, "diets": {}}},
        }
        response = authenticated_client.post(
            reverse("dailyorder-list"), payload, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        prevadzka.refresh_from_db()
        assert prevadzka.auto_order_paused is False

    def test_patch_to_zero_pauses_prevadzka(self, authenticated_client, user):
        prevadzka = user.profile.dostupne_prevadzky().first()
        order = DailyOrder.objects.create(
            user=user,
            prevadzka=prevadzka,
            date=FUTURE_ORDER_DATE,
            status="submitted",
            data={"lunch": {"menuCounts": {"A": 2}, "diets": {}}},
        )

        url = reverse("dailyorder-detail", kwargs={"pk": order.pk})
        response = authenticated_client.patch(
            url,
            {"data": {"lunch": {"menuCounts": {"A": 0}, "diets": {}}}},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        prevadzka.refresh_from_db()
        assert prevadzka.auto_order_paused is True

    def test_end_to_end_zero_order_stops_auto_copy_for_all_future_days(
        self, authenticated_client, user
    ):
        """Regression: zeroing today's order must not just skip tomorrow's
        auto-copy but permanently break the chain, so an older non-empty
        order is never used as a template further down the line either."""
        from api.services import apply_auto_orders

        prevadzka = user.profile.dostupne_prevadzky().first()
        older_date = FUTURE_ORDER_DATE - timedelta(days=7)
        reset_date = FUTURE_ORDER_DATE - timedelta(days=1)
        DailyOrder.objects.create(
            user=user,
            prevadzka=prevadzka,
            date=older_date,
            data={"lunch": {"menuCounts": {"A": 5}, "diets": {}}},
        )

        payload = {
            "date": str(reset_date),
            "status": "submitted",
            "data": {"lunch": {"menuCounts": {"A": 0}, "diets": {}}},
        }
        response = authenticated_client.post(
            reverse("dailyorder-list"), payload, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED

        result = apply_auto_orders(target_date=FUTURE_ORDER_DATE)

        assert user.email not in result["created"]
        assert not DailyOrder.objects.filter(
            prevadzka=prevadzka, date=FUTURE_ORDER_DATE
        ).exists()
