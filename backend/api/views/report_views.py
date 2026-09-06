import datetime
import logging

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .. import sections
from ..models import Celok, DailyOrder, Prevadzka
from ..permissions import IsAdminOrAbove, SectionAccess
from ..services import ReportService
from ..utils import meal_counts, order_row_label
from .report_helpers import build_user_meal_row, merge_meal_totals

logger = logging.getLogger(__name__)


def build_prevadzka_overview(target_date):
    """Payload pre prehľad dodania podkladov za deň.

    Zdieľané JSON endpointom aj XLSX/PDF exportmi, nech sa logika (klasifikácia
    edupage/app, počty, flagy) nerozchádza medzi výstupmi.
    """
    prevadzky = (
        Prevadzka.objects.filter(is_active=True)
        .select_related("celok")
        .order_by("celok__nazov", "sort_order", "nazov")
    )

    orders_by_prevadzka = {
        order.prevadzka_id: order
        for order in DailyOrder.objects.filter(
            date=target_date, prevadzka__isnull=False
        )
    }

    edupage_rows = []
    app_rows = []
    for prevadzka in prevadzky:
        is_edupage = prevadzka.celok.zdroj_objednavok == Celok.ZdrojObjednavok.EDUPAGE
        order = orders_by_prevadzka.get(prevadzka.id)
        data = {}
        flags = {
            "attention": [],
            "config_notes": [],
            "unmapped_diets": [],
            "uncertain_diets": [],
        }
        counts = meal_counts(data)
        delivery_status = "missing"
        if order is not None:
            data = order.data if isinstance(order.data, dict) else {}
            counts = meal_counts(data)
            if order.is_auto:
                delivery_status = "auto"
            elif counts["total"] == 0:
                delivery_status = "manual_zero"
            else:
                delivery_status = "manual"
            if isinstance(order.scrape_flags, dict):
                flags = {
                    "attention": order.scrape_flags.get("attention", []) or [],
                    "config_notes": order.scrape_flags.get("config_notes", []) or [],
                    "unmapped_diets": order.scrape_flags.get("unmapped_diets", [])
                    or [],
                    "uncertain_diets": order.scrape_flags.get("uncertain_diets", [])
                    or [],
                }

        row = {
            "prevadzka_id": prevadzka.id,
            "nazov": prevadzka.nazov,
            "celok": prevadzka.celok.nazov,
            "delivered": order is not None,
            "delivery_status": delivery_status,
            # Nastavenia zobrazované ako rýchle odznaky v prehľade prevádzok.
            # Frontend podľa zdroja objednávok vyberie relevantný prepínač ZV:
            # app = ručné balenie zvlášť, EduPage = automaticky dospelí zvlášť.
            "pack_separately_enabled": prevadzka.pack_separately_enabled,
            "adults_pack_separately_enabled": prevadzka.adults_pack_separately_enabled,
            "olovrant_s_obedom": prevadzka.olovrant_s_obedom,
            "counts": counts,
            "flags": flags,
            "has_warning": bool(
                flags["attention"]
                or flags["config_notes"]
                or flags["unmapped_diets"]
                or flags["uncertain_diets"]
            ),
        }
        (edupage_rows if is_edupage else app_rows).append(row)

    return {
        "date": target_date.isoformat(),
        "edupage": edupage_rows,
        "app": app_rows,
    }


@extend_schema_view(
    daily_stats=extend_schema(tags=["admin"]),
    daily_report=extend_schema(tags=["admin"]),
    prevadzka_overview=extend_schema(tags=["admin"]),
)
class AdminSummaryViewSet(viewsets.ViewSet):
    """
    Admin ViewSet for Dashboard Summaries.
    Aggregates order data for reporting and analytics.
    """

    permission_classes = [IsAdminOrAbove, SectionAccess]
    section = sections.PODKLADY

    def _parse_date(self, request):
        """Parse ?date=YYYY-MM-DD; vráti date alebo DRF Response(400)."""
        date_str = request.query_params.get("date")
        if not date_str:
            return Response(
                {"error": "date parameter required"}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            return datetime.date.fromisoformat(date_str)
        except (TypeError, ValueError):
            return Response(
                {"error": "invalid date format, expected YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["get"], url_path="daily-stats")
    def daily_stats(self, request):
        """Get daily order statistics for a given date.

        Delegates aggregation to ReportService. Results are cached for 5 minutes.
        """
        from ..cache_service import (
            DAILY_STATS_TIMEOUT,
            get_cached,
            get_daily_stats_cache_key,
            set_cached,
        )

        date_str = request.query_params.get("date")
        if not date_str:
            return Response(
                {"error": "Date parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = get_daily_stats_cache_key(date_str)
        cached_stats = get_cached(cache_key)
        if cached_stats is not None:
            return Response(cached_stats, status=status.HTTP_200_OK)

        stats = ReportService.aggregate_daily_stats(target_date)
        set_cached(cache_key, stats, timeout=DAILY_STATS_TIMEOUT)

        return Response(stats)

    @action(detail=False, methods=["get"], url_path="daily-report")
    def daily_report(self, request):
        """Get per-user order summary for a given date."""
        date_str = request.query_params.get("date")
        if not date_str:
            return Response(
                {"error": "date parameter required"}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            target_date = datetime.date.fromisoformat(date_str)
        except (TypeError, ValueError):
            return Response(
                {"error": "invalid date format, expected YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        orders = (
            DailyOrder.objects.filter(date=target_date)
            .select_related("user", "user__profile", "prevadzka__celok")
            .prefetch_related("prevadzka__celok__prevadzky")
            .order_by("user__email", "prevadzka__sort_order", "prevadzka__nazov")
        )

        totals = {
            "breakfast": {"menus": {}, "diets": {}, "total": 0},
            "lunch": {"menus": {}, "diets": {}, "total": 0},
            "olovrant": {"menus": {}, "diets": {}, "total": 0},
            "grand": 0,
        }
        rows = []
        for order in orders:
            user = order.user
            data = order.data if isinstance(order.data, dict) else {}
            bf = build_user_meal_row(data, "breakfast")
            lu = build_user_meal_row(data, "lunch")
            ol = build_user_meal_row(data, "olovrant")
            row_total = bf["total"] + lu["total"] + ol["total"]
            visible_meals = getattr(order.prevadzka, "visible_meals", None) or [
                "breakfast",
                "lunch",
                "olovrant",
            ]
            rows.append(
                {
                    # Riadok je na objednávku (teda na prevádzku), nie na
                    # používateľa — EduPage prevádzky zdieľajú jeden systémový
                    # login, takže `user_id` riadky nerozlíši.
                    "order_id": order.id,
                    "user_id": user.id,
                    "name": order_row_label(order),
                    "email": user.email,
                    "breakfast": bf,
                    "lunch": lu,
                    "olovrant": ol,
                    "visible_meals": visible_meals,
                    "total": row_total,
                }
            )
            merge_meal_totals(totals["breakfast"], bf)
            merge_meal_totals(totals["lunch"], lu)
            merge_meal_totals(totals["olovrant"], ol)
            totals["grand"] += row_total

        return Response(
            {"date": target_date.isoformat(), "rows": rows, "totals": totals}
        )

    @action(detail=False, methods=["get"], url_path="prevadzka-overview")
    def prevadzka_overview(self, request):
        """Prehľad dodania podkladov za deň, rozdelený na EduPage a in-app prevádzky.

        Pre každú aktívnu prevádzku vráti, či za daný deň existuje objednávka
        (`delivered`), počty raňajok/obedov/olovrantov a prípadné upozornenia
        zo scrapu (`flags`), z ktorých frontend vyrobí ✅ / ❌ / ⚠️.
        """
        parsed = self._parse_date(request)
        if isinstance(parsed, Response):
            return parsed
        return Response(build_prevadzka_overview(parsed))
