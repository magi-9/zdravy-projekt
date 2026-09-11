import datetime
import logging

from django.db import transaction
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from .. import sections
from ..edupage_scraper import (
    EdupageScraper,
    allowed_diet_names,
    build_prevadzka_matches,
    nest_order_data_by_category,
    prevadzky_without_match,
)
from ..management.commands.repoint_deduplicated_diets_2026_09 import MAPPINGS
from ..models import DailyOrder, EdupageConnection, EventLog
from ..permissions import IsAdminOrAbove, SectionAccess
from ..serializers import DailyOrderSerializer
from ..services.edupage_connection_service import edupage_operations
from ..services.event_log_service import build_model_diff, log_event
from ..utils import filter_order_data_for_prevadzka

logger = logging.getLogger(__name__)

EDUPAGE_SCRAPE_ERROR = (
    "Edupage scraping failed. Check the configured URL and try again."
)
EDUPAGE_TEST_URL_ERROR = "URL could not be reached or parsed."


class EdupageConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EdupageConnection
        fields = ["id", "name", "mealsguest_url", "api_identifier", "is_active"]


class AdminEdupageConnectionViewSet(viewsets.ModelViewSet):
    queryset = EdupageConnection.objects.all().order_by("name", "pk")
    serializer_class = EdupageConnectionSerializer
    permission_classes = [IsAdminOrAbove, SectionAccess]
    section = sections.PREVADZKY
    pagination_class = None

    AUDITED_FIELDS = {"api_identifier", "mealsguest_url", "is_active"}

    def _audit_data(self, serializer):
        return {
            key: value
            for key, value in serializer.validated_data.items()
            if key in self.AUDITED_FIELDS
        }

    def _log_change(self, instance, changes, action):
        if not changes:
            return
        log_event(
            EventLog.EventType.SETTINGS_CHANGE,
            actor=self.request.user,
            summary=f"Admin {action} EduPage pripojenie: {instance.name}.",
            payload={
                "model": instance._meta.label_lower,
                "object_id": instance.pk,
                "changes": changes,
            },
        )

    def perform_create(self, serializer):
        changes = build_model_diff(None, self._audit_data(serializer))
        instance = serializer.save()
        self._log_change(instance, changes, "vytvoril")

    def perform_update(self, serializer):
        changes = build_model_diff(serializer.instance, self._audit_data(serializer))
        instance = serializer.save()
        self._log_change(instance, changes, "upravil")

    @action(detail=False, methods=["post"], url_path="scrape")
    def scrape(self, request: Request) -> Response:
        """
        Scrape mealsGuest HTML for one or all EduPage connections for a given date
        and upsert the result as DailyOrder records.

        Body: { "date": "YYYY-MM-DD", "connection_id": <int> (optional) }
        When connection_id is omitted, all active EduPage connections are scraped.
        """
        date_str = request.data.get("date")
        connection_id = request.data.get("connection_id")

        if not date_str:
            return Response(
                {"error": "date is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            target_date = datetime.date.fromisoformat(date_str)
        except ValueError:
            return Response(
                {"error": "date must be YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST
            )

        # The action imports one date across all matching prevádzky. Reject the
        # whole request before scraping so a closed day's snapshot stays immutable.
        DailyOrderSerializer._enforce_day_open(target_date)

        operations = edupage_operations(connection_id=connection_id)
        if connection_id and not operations:
            return Response(
                {"error": f"Edupage connection {connection_id} not found"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        results = []
        scraper = EdupageScraper()
        allowed_diets = allowed_diet_names()

        for operation in operations:
            prevadzky = list(operation["prevadzky"])
            if not prevadzky:
                results.append(
                    {
                        "connection_id": operation["connection_id"],
                        "name": operation["name"],
                        "status": "skipped",
                        "reason": "no active prevadzka",
                    }
                )
                continue

            by_nazov = {p.nazov: p for p in prevadzky}
            visible_diets_by_prevadzka = {
                (p.nazov if len(prevadzky) > 1 else ""): set(
                    p.visible_diets.values_list("name", flat=True)
                )
                for p in prevadzky
            }
            matches = build_prevadzka_matches(prevadzky)
            bez_matchu = prevadzky_without_match(prevadzky)
            if len(prevadzky) > 1 and bez_matchu:
                results.append(
                    {
                        "connection_id": operation["connection_id"],
                        "name": operation["name"],
                        "status": "skipped",
                        "reason": (
                            "multi-prevadzka operation is missing edupage_match: "
                            + ", ".join(bez_matchu)
                        ),
                    }
                )
                continue

            try:
                result = scraper.scrape(
                    operation["url"],
                    target_date,
                    prevadzka_matches=matches if len(prevadzky) > 1 else None,
                    allowed_diets=allowed_diets,
                    canonical_diet_names=dict(MAPPINGS),
                    visible_diets_by_prevadzka=visible_diets_by_prevadzka,
                )
            except Exception:
                logger.exception(
                    "Scrape failed for connection %s", operation["connection_id"]
                )
                results.append(
                    {
                        "connection_id": operation["connection_id"],
                        "name": operation["name"],
                        "status": "error",
                        "error": EDUPAGE_SCRAPE_ERROR,
                    }
                )
                continue

            if not result.order_data:
                results.append(
                    {
                        "connection_id": operation["connection_id"],
                        "name": operation["name"],
                        "status": "empty",
                        "warnings": result.warnings,
                    }
                )
                continue

            # Zápis blokujú len štrukturálne warningy. Neznáma diéta ho nezastaví —
            # porcie sú započítané pod názvom z EduPage a vrátia sa v
            # `unmapped_letters`, nech ju admin vie založiť v appke.
            if result.warnings:
                results.append(
                    {
                        "connection_id": operation["connection_id"],
                        "name": operation["name"],
                        "status": "skipped",
                        "warnings": result.warnings,
                        "unmapped_letters": result.unmapped_letters,
                    }
                )
                continue

            data_by_nazov = (
                result.order_data_by_prevadzka
                if len(prevadzky) > 1
                else {prevadzky[0].nazov: result.order_data}
            )

            written = []
            with transaction.atomic():
                for nazov, prevadzka in by_nazov.items():
                    order_data = nest_order_data_by_category(
                        data_by_nazov.get(nazov, {}), nazov
                    )
                    order_data = filter_order_data_for_prevadzka(order_data, nazov)
                    order, created = DailyOrder.objects.update_or_create(
                        prevadzka=prevadzka,
                        date=target_date,
                        defaults={"user": operation["user"], "data": order_data},
                    )
                    written.append(
                        {
                            "prevadzka": nazov,
                            "status": "created" if created else "updated",
                            "order_id": order.pk,
                        }
                    )

            results.append(
                {
                    "connection_id": operation["connection_id"],
                    "name": operation["name"],
                    "status": "updated",
                    "orders": written,
                    "warnings": result.warnings,
                    "unmapped_letters": result.unmapped_letters,
                    "config_notes": result.config_notes,
                    "attention": result.attention,
                }
            )

        return Response({"date": date_str, "results": results})

    @action(detail=False, methods=["post"], url_path="test-url")
    def test_url(self, request: Request) -> Response:
        """
        Diagnostic endpoint: test whether a mealsGuest URL is reachable and parseable.

        Body: { "url": "https://school.edupage.org/menu/mealsGuest?id=TOKEN" }
        Always returns HTTP 200; use the `ok` field to check success.
        """
        url = request.data.get("url", "").strip()
        if not url:
            return Response({"ok": False, "error": "url is required"})
        if not url.startswith("https://"):
            return Response({"ok": False, "error": "url must start with https://"})

        try:
            result = EdupageScraper().scrape(
                url, datetime.date.today(), allowed_diets=allowed_diet_names()
            )
        except Exception:
            logger.warning("test_url failed for %s", url, exc_info=True)
            return Response({"ok": False, "error": EDUPAGE_TEST_URL_ERROR})

        total = sum(
            meal.get("menuCounts", {}).get("A", 0)
            for meal in result.order_data.values()
        )
        return Response(
            {
                "ok": True,
                "total_portions": total,
                "meals": list(result.order_data.keys()),
                "warnings": result.warnings,
                "unmapped_letters": result.unmapped_letters,
            }
        )
