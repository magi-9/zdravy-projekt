import datetime

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status

from api.models import DailyOrder, UserProfile

pytestmark = pytest.mark.integration


NON_EMPTY_DATA = {
    "breakfast": {"Dospelý": {"menuCounts": {"A": 1}, "diets": {}}},
    "lunch": {"Dospelý": {"menuCounts": {"B": 2}, "diets": {}}},
    "olovrant": {},
}

EMPTY_DATA = {
    "breakfast": {"Dospelý": {"menuCounts": {"A": 0}, "diets": {}}},
    "lunch": {},
    "olovrant": {},
}

# Reference dates kept in the future so unrelated tests are not blocked by
# runtime deadline enforcement.
MONDAY = datetime.date(2099, 1, 5)
TUESDAY = datetime.date(2099, 1, 6)
WEDNESDAY = datetime.date(2099, 1, 7)
THURSDAY = datetime.date(2099, 1, 8)
FRIDAY = datetime.date(2099, 1, 9)
SATURDAY = datetime.date(2099, 1, 10)
SUNDAY = datetime.date(2099, 1, 11)


@pytest.mark.django_db
class TestOrderCreation:
    """Test order creation via POST /api/orders/"""

    def test_create_order_with_data(self, authenticated_client, user):
        """User can create an order with meal data."""
        url = reverse("dailyorder-list")
        data = {"date": str(MONDAY), "data": NON_EMPTY_DATA}
        response = authenticated_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert DailyOrder.objects.count() == 1
        order = DailyOrder.objects.get()
        assert order.user == user
        assert order.date == MONDAY
        assert order.data == NON_EMPTY_DATA
        assert order.status == "submitted"
        assert order.is_auto is False

    def test_create_order_empty_data(self, authenticated_client, user):
        """User can create an order with empty data."""
        url = reverse("dailyorder-list")
        data = {"date": str(MONDAY), "data": {}}
        response = authenticated_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        order = DailyOrder.objects.get()
        assert order.data == {}

    def test_create_order_requires_date(self, authenticated_client):
        """Order creation requires a date field."""
        url = reverse("dailyorder-list")
        data = {"data": NON_EMPTY_DATA}
        response = authenticated_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_order_requires_authentication(self, api_client):
        """Unauthenticated users cannot create orders."""
        url = reverse("dailyorder-list")
        response = api_client.post(url, {"date": str(MONDAY)}, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_staff_cannot_create_orders(self, admin_client, admin_user):
        """Staff/admin users cannot place orders."""
        url = reverse("dailyorder-list")
        response = admin_client.post(
            url, {"date": str(MONDAY), "data": NON_EMPTY_DATA}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_order_different_dates(self, authenticated_client, user):
        """User can create orders for multiple dates."""
        url = reverse("dailyorder-list")
        response1 = authenticated_client.post(
            url, {"date": str(MONDAY), "data": NON_EMPTY_DATA}, format="json"
        )
        response2 = authenticated_client.post(
            url, {"date": str(TUESDAY), "data": EMPTY_DATA}, format="json"
        )

        assert response1.status_code == status.HTTP_201_CREATED
        assert response2.status_code == status.HTTP_201_CREATED
        assert DailyOrder.objects.count() == 2


@pytest.mark.django_db
class TestOrderUpdate:
    """Test order updates via upsert logic."""

    def test_update_existing_order(self, authenticated_client, user):
        """POST same date should update existing order."""
        url = reverse("dailyorder-list")
        # Create initial order
        DailyOrder.objects.create(user=user, date=MONDAY, data=EMPTY_DATA)

        # Update with new data
        new_data = {"breakfast": {"Dospelý": {"menuCounts": {"A": 5}, "diets": {}}}}
        response = authenticated_client.post(
            url, {"date": str(MONDAY), "data": new_data}, format="json"
        )

        assert response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]
        assert DailyOrder.objects.count() == 1
        order = DailyOrder.objects.get()
        assert order.data == new_data

    def test_manual_submit_over_auto_order_clears_is_auto(
        self, authenticated_client, user
    ):
        """Issue #507: submitting real data over an auto-generated placeholder
        (created by auto_order_service after deadline, `is_auto=True`) must
        clear the flag — otherwise the admin overview keeps flagging it "na
        kontrolu" forever, even after the client actually filled it in."""
        url = reverse("dailyorder-list")
        DailyOrder.objects.create(user=user, date=MONDAY, data=EMPTY_DATA, is_auto=True)

        response = authenticated_client.post(
            url, {"date": str(MONDAY), "data": NON_EMPTY_DATA}, format="json"
        )

        assert response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]
        order = DailyOrder.objects.get()
        assert order.data == NON_EMPTY_DATA
        assert order.is_auto is False

    def test_patch_over_auto_order_clears_is_auto(self, authenticated_client, user):
        """Same as above, via PATCH (DailyOrderSerializer.update())."""
        order = DailyOrder.objects.create(
            user=user, date=MONDAY, data=EMPTY_DATA, is_auto=True
        )

        url = reverse("dailyorder-detail", args=[order.id])
        response = authenticated_client.patch(
            url, {"data": NON_EMPTY_DATA}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        order.refresh_from_db()
        assert order.data == NON_EMPTY_DATA
        assert order.is_auto is False

    def test_user_can_only_update_own_orders(self, authenticated_client, user):
        """User cannot update another user's order."""
        other_user = User.objects.create_user(
            username="other@example.com", email="other@example.com", password="pass123"
        )
        # Objednávky sú per prevádzka (NOT NULL); profil dá klientovi celok
        # a jednu prevádzku, ktorú DailyOrder.save() doplní automaticky.
        UserProfile.objects.get_or_create(
            user=other_user, defaults={"company_name": other_user.email}
        )
        order = DailyOrder.objects.create(user=other_user, date=MONDAY, data=EMPTY_DATA)

        # Try to update other user's order
        url = reverse("dailyorder-detail", args=[order.id])
        response = authenticated_client.patch(
            url, {"data": NON_EMPTY_DATA}, format="json"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestTouchedMeals:
    """`touched_meals` (Jarabinka 11.9.2026) — jedlo, ktoré klient/admin
    v zápise skutočne riešil (aj na nulu), sa musí uložiť a naprieč ďalšími
    zápismi na ten istý deň len zjednocovať, nikdy strácať."""

    def test_create_persists_touched_meals(self, authenticated_client, user):
        url = reverse("dailyorder-list")
        response = authenticated_client.post(
            url,
            {"date": str(MONDAY), "data": {}, "touched_meals": ["lunch"]},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        order = DailyOrder.objects.get()
        assert order.touched_meals == ["lunch"]

    def test_touched_meals_default_empty(self, authenticated_client, user):
        """Bez `touched_meals` v requeste (staré klienty, iné integrácie)
        ostáva pole prázdne — spätne kompatibilné."""
        url = reverse("dailyorder-list")
        response = authenticated_client.post(
            url, {"date": str(MONDAY), "data": NON_EMPTY_DATA}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        order = DailyOrder.objects.get()
        assert order.touched_meals == []

    def test_second_post_unions_touched_meals(self, authenticated_client, user):
        """Deň sa rieši postupne (raňajky večer, obed ráno) — druhý POST na
        ten istý deň nesmie stratiť, čo bolo touched skôr."""
        url = reverse("dailyorder-list")
        authenticated_client.post(
            url,
            {"date": str(MONDAY), "data": {}, "touched_meals": ["breakfast"]},
            format="json",
        )

        response = authenticated_client.post(
            url,
            {"date": str(MONDAY), "data": {}, "touched_meals": ["lunch"]},
            format="json",
        )

        assert response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]
        order = DailyOrder.objects.get()
        assert set(order.touched_meals) == {"breakfast", "lunch"}

    def test_patch_unions_touched_meals(self, authenticated_client, user):
        order = DailyOrder.objects.create(
            user=user, date=MONDAY, data=EMPTY_DATA, touched_meals=["breakfast"]
        )

        url = reverse("dailyorder-detail", args=[order.id])
        response = authenticated_client.patch(
            url, {"data": NON_EMPTY_DATA, "touched_meals": ["lunch"]}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        order.refresh_from_db()
        assert set(order.touched_meals) == {"breakfast", "lunch"}

    def test_invalid_meal_key_rejected(self, authenticated_client, user):
        url = reverse("dailyorder-list")
        response = authenticated_client.post(
            url,
            {"date": str(MONDAY), "data": {}, "touched_meals": ["desiata"]},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestOrderRetrieval:
    """Test order retrieval endpoints."""

    def test_get_order_by_date(self, authenticated_client, user):
        """User can retrieve order by date."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)

        url = reverse("dailyorder-by-date", args=[MONDAY])
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"] == NON_EMPTY_DATA
        assert response.data["date"] == str(MONDAY)

    def test_get_nonexistent_order_returns_empty(self, authenticated_client):
        """Nonexistent order returns empty data dict."""
        url = reverse("dailyorder-by-date", args=[MONDAY])
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"] == {}

    def test_list_orders_filtered_by_user(self, authenticated_client, user):
        """User can only see their own orders in list."""
        other_user = User.objects.create_user(
            username="other@example.com", email="other@example.com", password="pass123"
        )
        # Objednávky sú per prevádzka (NOT NULL); profil dá klientovi celok
        # a jednu prevádzku, ktorú DailyOrder.save() doplní automaticky.
        UserProfile.objects.get_or_create(
            user=other_user, defaults={"company_name": other_user.email}
        )
        user_order = DailyOrder.objects.create(
            user=user, date=MONDAY, data=NON_EMPTY_DATA
        )
        other_order = DailyOrder.objects.create(
            user=other_user, date=TUESDAY, data=NON_EMPTY_DATA
        )

        url = reverse("dailyorder-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # Response is paginated
        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == user_order.id

    def test_list_orders_honours_page_size_param(self, authenticated_client, user):
        """ClientDetail dashboard chce natiahnuť len pár posledných objednávok
        (`?page_size=3`) bez toho, aby si musela ťahať celú stránkovanú
        históriu — pozri `DailyOrderPagination`."""
        for offset in range(5):
            DailyOrder.objects.create(
                user=user,
                date=MONDAY + datetime.timedelta(days=offset),
                data=NON_EMPTY_DATA,
            )

        url = reverse("dailyorder-list")
        response = authenticated_client.get(url, {"page_size": 3})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 5
        assert len(response.data["results"]) == 3
        assert response.data["next"] is not None


@pytest.mark.django_db
class TestOrderValidation:
    """Test order validation rules."""

    def test_unique_constraint_user_date(self, authenticated_client, user):
        """Cannot create duplicate orders for same user/date via unique constraint."""
        DailyOrder.objects.create(user=user, date=MONDAY, data=EMPTY_DATA)

        # Try to create another for same date
        url = reverse("dailyorder-list")
        response = authenticated_client.post(
            url, {"date": str(MONDAY), "data": EMPTY_DATA}, format="json"
        )

        # Should upsert or succeed with update semantics
        # Depending on serializer implementation
        assert DailyOrder.objects.filter(user=user, date=MONDAY).count() == 1

    def test_invalid_date_format(self, authenticated_client):
        """Invalid date format is rejected."""
        url = reverse("dailyorder-list")
        response = authenticated_client.post(
            url, {"date": "invalid-date", "data": {}}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_order_with_complex_meal_data(self, authenticated_client, user):
        """Order can store complex nested meal structures."""
        complex_data = {
            "breakfast": {
                "Dospelý": {
                    "menuCounts": {"A": 2, "B": 1},
                    "diets": {"Vegetariánske": 1},
                },
                "Deti": {"menuCounts": {"A": 1}, "diets": {}},
            },
            "lunch": {
                "Dospelý": {"menuCounts": {"A": 5, "B": 3}, "diets": {"Vegánske": 2}}
            },
            "olovrant": {},
        }

        url = reverse("dailyorder-list")
        response = authenticated_client.post(
            url, {"date": str(MONDAY), "data": complex_data}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        order = DailyOrder.objects.get()
        assert order.data == complex_data


@pytest.mark.django_db
class TestPlannedOrdersEndpoint:
    """Test GET /api/orders/planned/ endpoint."""

    def test_planned_orders_returns_five_workdays(self, authenticated_client):
        """Planned orders endpoint returns 5 upcoming workdays."""
        url = reverse("planned-orders-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 5
        # All dates should be workdays (Mon-Fri)
        for item in response.data:
            day_date = datetime.date.fromisoformat(item["date"])
            assert day_date.weekday() < 5  # 0-4 = Mon-Fri

    def test_planned_orders_excludes_weekends(self, authenticated_client):
        """Planned orders never include Saturday or Sunday."""
        url = reverse("planned-orders-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        for item in response.data:
            day_date = datetime.date.fromisoformat(item["date"])
            assert day_date.weekday() not in [5, 6]  # 5=Sat, 6=Sun

    def test_planned_orders_shows_existing_orders(self, authenticated_client, user):
        """Existing orders show exists=True in planned orders."""
        # Create order for first workday in planned range
        url = reverse("planned-orders-list")
        response = authenticated_client.get(url)
        first_date = datetime.date.fromisoformat(response.data[0]["date"])

        DailyOrder.objects.create(user=user, date=first_date, data=NON_EMPTY_DATA)

        response = authenticated_client.get(url)
        first_item = response.data[0]
        assert first_item["exists"] is True
        assert first_item["is_empty"] is False

    def test_planned_orders_shows_auto_flag(self, authenticated_client, user):
        """Auto-generated orders show is_auto=True."""
        url = reverse("planned-orders-list")
        response = authenticated_client.get(url)
        first_date = datetime.date.fromisoformat(response.data[0]["date"])

        DailyOrder.objects.create(
            user=user, date=first_date, data=NON_EMPTY_DATA, is_auto=True
        )

        response = authenticated_client.get(url)
        assert response.data[0]["is_auto"] is True

    def test_planned_orders_total_portions(self, authenticated_client, user):
        """Planned orders calculate total portions correctly."""
        url = reverse("planned-orders-list")
        response = authenticated_client.get(url)
        first_date = datetime.date.fromisoformat(response.data[0]["date"])

        data = {
            "breakfast": {"Dospelý": {"menuCounts": {"A": 2}, "diets": {}}},
            "lunch": {"Dospelý": {"menuCounts": {"B": 3}, "diets": {}}},
            "olovrant": {"Dospelý": {"menuCounts": {"C": 1}, "diets": {}}},
        }
        DailyOrder.objects.create(user=user, date=first_date, data=data)

        response = authenticated_client.get(url)
        assert response.data[0]["totalPortions"] == 6  # 2 + 3 + 1
        assert response.data[0]["mealCount"]["breakfast"] == 2
        assert response.data[0]["mealCount"]["lunch"] == 3
        assert response.data[0]["mealCount"]["olovrant"] == 1

    def test_planned_orders_requires_authentication(self, api_client):
        """Planned orders endpoint requires authentication."""
        url = reverse("planned-orders-list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_planned_orders_staff_can_access(self, admin_client):
        """Admin/staff can access planned orders endpoint."""
        url = reverse("planned-orders-list")
        response = admin_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 5


@pytest.mark.django_db
class TestOrderDeletion:
    """Test order deletion."""

    def test_delete_order(self, authenticated_client, user):
        """User can delete their own order."""
        order = DailyOrder.objects.create(user=user, date=MONDAY, data=NON_EMPTY_DATA)

        url = reverse("dailyorder-detail", args=[order.id])
        response = authenticated_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert DailyOrder.objects.count() == 0

    def test_delete_nonexistent_order_fails(self, authenticated_client):
        """Deleting nonexistent order returns 404."""
        url = reverse("dailyorder-detail", args=[99999])
        response = authenticated_client.delete(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cannot_delete_other_user_order(self, authenticated_client):
        """User cannot delete another user's order."""
        other_user = User.objects.create_user(
            username="other@example.com", email="other@example.com", password="pass123"
        )
        # Objednávky sú per prevádzka (NOT NULL); profil dá klientovi celok
        # a jednu prevádzku, ktorú DailyOrder.save() doplní automaticky.
        UserProfile.objects.get_or_create(
            user=other_user, defaults={"company_name": other_user.email}
        )
        order = DailyOrder.objects.create(
            user=other_user, date=MONDAY, data=NON_EMPTY_DATA
        )

        url = reverse("dailyorder-detail", args=[order.id])
        response = authenticated_client.delete(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert DailyOrder.objects.count() == 1  # Order still exists


@pytest.mark.django_db
class TestOrderEmpty:
    """Test empty order detection and logic."""

    def test_zero_portions_is_empty(self, authenticated_client, user):
        """Order with all zero portions shows as empty."""
        from django.utils import timezone

        # Use localdate() to match the view's timezone (Europe/Bratislava).
        today = timezone.localdate()
        test_date = today
        while test_date.weekday() >= 5:
            test_date += datetime.timedelta(days=1)

        DailyOrder.objects.create(user=user, date=test_date, data=EMPTY_DATA)

        url = reverse("planned-orders-list")
        response = authenticated_client.get(url)

        item = next(
            (item for item in response.data if item["date"] == str(test_date)), None
        )
        assert item is not None
        assert item["is_empty"] is True

    def test_any_positive_portion_not_empty(self, authenticated_client, user):
        """Order with any positive portion shows as not empty."""
        from django.utils import timezone

        # Use localdate() to match the view's timezone (Europe/Bratislava).
        today = timezone.localdate()
        test_date = today
        while test_date.weekday() >= 5:
            test_date += datetime.timedelta(days=1)

        DailyOrder.objects.create(user=user, date=test_date, data=NON_EMPTY_DATA)

        url = reverse("planned-orders-list")
        response = authenticated_client.get(url)

        item = next(
            (item for item in response.data if item["date"] == str(test_date)), None
        )
        assert item is not None
        assert item["is_empty"] is False
