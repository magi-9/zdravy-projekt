"""
Concurrency tests for DailyOrder submission.

These tests simulate race conditions that occur when multiple requests submit
an order for the same (user, date) simultaneously.  Because true OS-level
parallelism is hard to guarantee inside a single pytest process, we exercise
the logical paths by:

  1. Direct serializer / service calls that replicate the interleaved-execution
     scenario (IntegrityError on INSERT → retry with select_for_update).
  2. A threading-based smoke test that fires N concurrent API requests and
     asserts exactly one row is created and no uncaught exceptions are raised.
"""

import datetime
import threading
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.urls import reverse
from rest_framework.test import APIClient

from api.models import DailyOrder
from api.serializers import DailyOrderSerializer

pytestmark = pytest.mark.integration

TARGET_DATE = datetime.date(2099, 1, 5)

ORDER_DATA = {
    "breakfast": {"Dospelý": {"menuCounts": {"A": 2}, "diets": {}}},
    "lunch": {"Dospelý": {"menuCounts": {"B": 1}, "diets": {}}},
    "olovrant": {},
}


# ---------------------------------------------------------------------------
# Serializer-level unit tests (no HTTP layer)
# ---------------------------------------------------------------------------


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


def _make_serializer(data: dict, user: User) -> DailyOrderSerializer:
    """Build a DailyOrderSerializer with a mock request context for ``user``."""
    request = Mock()
    request.user = user
    return DailyOrderSerializer(data=data, context={"request": request})


@pytest.mark.django_db(transaction=True)
class TestSerializerConcurrency:
    """Validate the select_for_update / IntegrityError retry path."""

    def test_create_new_order_no_conflict(self, user):
        """Happy path: create succeeds without any lock contention."""
        serializer = _make_serializer(
            {"date": str(TARGET_DATE), "data": ORDER_DATA}, user
        )
        assert serializer.is_valid(), serializer.errors
        order = serializer.save(user=user)

        assert order.pk is not None
        assert order.date == TARGET_DATE
        assert order.status == "submitted"
        db_order = DailyOrder.objects.get(user=user, date=TARGET_DATE)
        assert db_order.data == ORDER_DATA

    def test_update_existing_order_no_conflict(self, user):
        """Happy path: update path via select_for_update.get() succeeds."""
        DailyOrder.objects.create(user=user, date=TARGET_DATE, data={})

        new_data = {"breakfast": {"Dospelý": {"menuCounts": {"A": 3}, "diets": {}}}}
        serializer = _make_serializer(
            {"date": str(TARGET_DATE), "data": new_data}, user
        )
        assert serializer.is_valid(), serializer.errors
        order = serializer.save(user=user)

        assert DailyOrder.objects.filter(user=user, date=TARGET_DATE).count() == 1
        assert order.data == new_data

    def test_create_existing_order_unions_touched_meals_from_locked_row(self, user):
        """Union sa robí až po locku, nie zo snapshotu pred ním."""
        existing = DailyOrder.objects.create(
            user=user,
            date=TARGET_DATE,
            data={},
            touched_meals=["breakfast"],
        )

        serializer = _make_serializer(
            {"date": str(TARGET_DATE), "data": {}, "touched_meals": ["lunch"]},
            user,
        )
        assert serializer.is_valid(), serializer.errors
        serializer.save(user=user)

        existing.refresh_from_db()
        assert existing.touched_meals == ["breakfast", "lunch"]

    def test_patch_unions_touched_meals_from_locked_row(self, user):
        order = DailyOrder.objects.create(
            user=user,
            date=TARGET_DATE,
            data={},
            touched_meals=["breakfast"],
        )
        request = Mock()
        request.user = user
        serializer = DailyOrderSerializer(
            order,
            data={"data": {}, "touched_meals": ["lunch"]},
            partial=True,
            context={"request": request},
        )
        assert serializer.is_valid(), serializer.errors
        serializer.save()

        order.refresh_from_db()
        assert order.touched_meals == ["breakfast", "lunch"]

    def test_integrity_error_retry_path(self, user):
        """
        Simulate the race: DoesNotExist → create() raises IntegrityError
        (another thread won the race) → retry with select_for_update.get().

        We verify that even when create() raises IntegrityError, the
        serializer still returns the existing row after the retry.
        """
        existing_order = DailyOrder.objects.create(
            user=user,
            date=TARGET_DATE,
            data={"lunch": {"Dospelý": {"menuCounts": {"A": 1}, "diets": {}}}},
        )

        # Patch DailyOrder.objects so:
        #   select_for_update().get() → DoesNotExist on first call (simulates the
        #     "gap" between read and write in a concurrent scenario)
        #   create() → raises IntegrityError
        #   The second select_for_update().get() returns the existing row
        original_manager = DailyOrder.objects

        get_call_count = {"n": 0}

        class FakeQS:
            def select_for_update(self, **kwargs):
                return self

            def get(self, **kwargs):
                get_call_count["n"] += 1
                if get_call_count["n"] == 1:
                    raise DailyOrder.DoesNotExist
                # Second call returns the existing row
                return existing_order

        class FakeManager:
            def select_for_update(self, **kwargs):
                return FakeQS()

            def create(self, **kwargs):
                raise IntegrityError("duplicate key")

            def filter(self, **kwargs):
                return original_manager.filter(**kwargs)

            def get(self, **kwargs):
                return original_manager.get(**kwargs)

        with patch.object(DailyOrder, "objects", FakeManager()):
            serializer = _make_serializer(
                {"date": str(TARGET_DATE), "data": ORDER_DATA}, user
            )
            assert serializer.is_valid(), serializer.errors
            order = serializer.save(user=user)

        assert order.pk == existing_order.pk
        assert (
            get_call_count["n"] == 2
        ), "Expected exactly 2 get() calls (first miss, retry)"

    def test_draft_status_deletes_existing_order(self, user):
        """Draft submission deletes the stored order (unchanged behaviour)."""
        DailyOrder.objects.create(user=user, date=TARGET_DATE, data=ORDER_DATA)

        serializer = _make_serializer(
            {"date": str(TARGET_DATE), "data": {}, "status": "draft"}, user
        )
        assert serializer.is_valid(), serializer.errors
        order = serializer.save(user=user)

        assert order.pk is None  # unsaved sentinel
        assert DailyOrder.objects.filter(user=user, date=TARGET_DATE).count() == 0


# ---------------------------------------------------------------------------
# Threading smoke-test (real DB, real HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestConcurrentHTTPSubmissions:
    """
    Spawn N threads each sending a POST /api/orders/ for the same (user, date).
    Only one row must exist in the DB at the end; all responses must be 2xx.
    """

    CONCURRENCY = 8

    def _make_client(self, user: User) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _submit(self, user: User, data: dict) -> int:
        client = self._make_client(user)
        url = reverse("dailyorder-list")
        resp = client.post(url, data, format="json")
        return resp.status_code

    def test_concurrent_submissions_single_row(self, user):
        """N concurrent POSTs for the same date create exactly one DB row."""
        payload = {"date": str(TARGET_DATE), "data": ORDER_DATA}
        results = []
        errors = []

        def worker():
            try:
                code = self._submit(user, payload)
                results.append(code)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(self.CONCURRENCY)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Unhandled exceptions in threads: {errors}"
        assert all(
            200 <= code < 300 for code in results
        ), f"Non-2xx responses: {results}"
        assert (
            DailyOrder.objects.filter(user=user, date=TARGET_DATE).count() == 1
        ), "Expected exactly one order row after concurrent submissions"

    def test_concurrent_updates_last_write_wins(self, user):
        """
        After N concurrent updates the DB ends up with exactly 1 row.
        We do not assert which data value "wins" — only that there is no
        duplicate row and no server error.
        """
        # Seed an existing order
        DailyOrder.objects.create(user=user, date=TARGET_DATE, data={})

        payloads = [
            {
                "date": str(TARGET_DATE),
                "data": {
                    "breakfast": {"Dospelý": {"menuCounts": {"A": i}, "diets": {}}},
                    "lunch": {},
                    "olovrant": {},
                },
            }
            for i in range(self.CONCURRENCY)
        ]

        status_codes = []
        errors = []

        def worker(payload):
            try:
                code = self._submit(user, payload)
                status_codes.append(code)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(p,)) for p in payloads]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Unhandled exceptions: {errors}"
        assert all(
            200 <= code < 300 for code in status_codes
        ), f"Non-2xx responses: {status_codes}"
        assert (
            DailyOrder.objects.filter(user=user, date=TARGET_DATE).count() == 1
        ), "Concurrent updates produced duplicate rows"


# ---------------------------------------------------------------------------
# auto_order_service idempotency under concurrent Celery task execution
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestAutoOrderServiceConcurrency:
    """
    Verify that apply_auto_orders() is idempotent when called concurrently.
    Two threads calling apply_auto_orders() for the same date must not
    duplicate rows for any client.
    """

    def test_concurrent_apply_auto_orders_no_duplicates(self, db):
        from api.services.auto_order_service import apply_auto_orders

        # Create clients with a historical order so auto-order logic triggers
        clients = []
        for i in range(3):
            u = _client_user(
                username=f"auto_user_{i}@example.com",
                email=f"auto_user_{i}@example.com",
                password="pass",
            )
            DailyOrder.objects.create(
                user=u,
                date=datetime.date(2025, 3, 7),  # a Friday before TARGET_DATE
                data=ORDER_DATA,
                status="submitted",
            )
            clients.append(u)

        target = datetime.date(2025, 3, 10)  # Monday
        results = []
        errors = []

        def run():
            try:
                results.append(apply_auto_orders(target))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        t1, t2 = threading.Thread(target=run), threading.Thread(target=run)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"Exceptions in auto_order threads: {errors}"

        for client in clients:
            count = DailyOrder.objects.filter(user=client, date=target).count()
            assert count == 1, f"Expected 1 auto-order for {client.email}, got {count}"
