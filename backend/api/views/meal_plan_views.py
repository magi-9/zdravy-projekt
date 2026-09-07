"""Views for the Jedálniček (Meal Plan) module."""

from __future__ import annotations

from urllib.parse import quote

from django.db.models import Prefetch
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from ..cache_service import get_cached, get_closed_day_pdf_cache_key
from ..models import (
    DailyMealPlan,
    Diet,
    DietComponentMerge,
    MealPlanItem,
    MealTemplate,
    PortionType,
)
from ..order_data import OrderData, safe_count
from ..permissions import IsAdminOrAbove, IsKuchynaOrAbove
from ..roles import is_admin_or_above
from ..serializers_menu import (
    DailyMealPlanSerializer,
    MealTemplateSerializer,
    PortionTypeSerializer,
)
from ..services.gramage_pdf_service import (
    get_cached_gramage_dashboard_data as _cached_gramage_dashboard_data,
)
from ..services.gramage_pdf_service import (
    render_gramage_dashboard_pdf,
)
from ..services.meal_plan_service import (
    DIET_COMPONENT_MERGE_MEALS,
    MealPlanService,
    diet_component_merge_board,
)
from ..utils import parse_date_param
from .audit_mixins import AuditedModelViewSetMixin

_XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _parse_bool_param(request, name: str, default: bool) -> bool:
    """Query-param booleans pre "Nastavenia tabuľky" (gramáž, 2.9.2026):
    chýbajúci parameter = `default`, "0"/"false"/"no" = False, čokoľvek iné
    (vrátane "1") = True."""
    raw = request.query_params.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no")


class PortionTypeViewSet(AuditedModelViewSetMixin, viewsets.ModelViewSet):
    """
    List portion types (age-group coefficients); non-staff see only active
    entries and cannot write. Staff can adjust an existing coefficient.
    """

    serializer_class = PortionTypeSerializer
    pagination_class = None

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsAdminOrAbove()]

    def get_queryset(self):
        qs = PortionType.objects.all()
        if not is_admin_or_above(self.request.user):
            qs = qs.filter(is_active=True)
        return qs


class MealTemplateViewSet(AuditedModelViewSetMixin, viewsets.ModelViewSet):
    """
    List meal templates (the fixed weight catalog); filterable by category.
    Non-staff see only active entries and cannot write. Staff can add a new
    catalog entry (e.g. a new "Hlavný chod 8") if the physical weight table
    ever gains a row, without needing a deploy/management command.
    """

    serializer_class = MealTemplateSerializer
    pagination_class = None

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [IsAdminOrAbove()]

    def get_queryset(self):
        qs = MealTemplate.objects.all()
        if not is_admin_or_above(self.request.user):
            qs = qs.filter(is_active=True)
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)
        return qs


@extend_schema_view(
    list=extend_schema(tags=["meal-plan"]),
    retrieve=extend_schema(tags=["meal-plan"]),
    create=extend_schema(tags=["meal-plan"]),
    update=extend_schema(tags=["meal-plan"]),
    partial_update=extend_schema(tags=["meal-plan"]),
    destroy=extend_schema(tags=["meal-plan"]),
)
class DailyMealPlanViewSet(AuditedModelViewSetMixin, viewsets.ModelViewSet):
    """Admin ViewSet for daily meal plans with gramage reporting and export."""

    serializer_class = DailyMealPlanSerializer

    def _is_admin_route(self) -> bool:
        return self.request.path.startswith("/api/admin/")

    #: Prehľady nakladania — kuchyňa ich len číta, meniť nesmie nič (#486).
    KUCHYNA_READABLE_ACTIONS = {"gramage_dashboard", "gramage_dashboard_pdf"}

    def get_permissions(self):
        if (
            self.action in ["list", "retrieve", "by_date"]
            and not self._is_admin_route()
        ):
            return [permissions.IsAuthenticated()]
        if self.action in self.KUCHYNA_READABLE_ACTIONS:
            return [IsKuchynaOrAbove()]
        return [IsAdminOrAbove()]

    def get_queryset(self):
        item_queryset = MealPlanItem.objects.select_related("template__diet", "diet")
        if not is_admin_or_above(self.request.user):
            item_queryset = item_queryset.filter(template__is_active=True)
        qs = DailyMealPlan.objects.prefetch_related(
            Prefetch("items", queryset=item_queryset),
            "enrolled_counts__portion_type",
        ).order_by("-date")
        if not is_admin_or_above(self.request.user):
            qs = qs.filter(items__template__is_active=True).distinct()
        from_date = self.request.query_params.get("from")
        to_date = self.request.query_params.get("to")
        if from_date:
            qs = qs.filter(date__gte=parse_date_param(from_date, "from"))
        if to_date:
            qs = qs.filter(date__lte=parse_date_param(to_date, "to"))
        return qs

    def perform_create(self, serializer):
        super().perform_create(serializer)

    def list(self, request, *args, **kwargs):
        if not self._is_admin_route():
            return super().list(request, *args, **kwargs)

        queryset = self.filter_queryset(self.get_queryset())
        payload = list(
            DailyMealPlanSerializer(
                queryset, many=True, context={"request": request}
            ).data
        )
        return Response(payload)

    @action(detail=False, methods=["get"], url_path="by-date")
    def by_date(self, request):
        """GET /api/admin/meal-plans/by-date/?date=YYYY-MM-DD"""
        date_str = request.query_params.get("date")
        if not date_str:
            return Response(
                {"error": "date query param required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        date = parse_date_param(date_str)

        try:
            plan = self.get_queryset().get(date=date)
        except DailyMealPlan.DoesNotExist:
            return Response(
                {
                    "exists": False,
                    "date": str(date),
                    "notes": "",
                    "items": [],
                }
            )

        return Response(
            {
                "exists": True,
                **DailyMealPlanSerializer(plan, context={"request": request}).data,
            }
        )

    @action(detail=True, methods=["get"], url_path="gramage-report")
    def gramage_report(self, request, pk=None):
        """GET /api/admin/meal-plans/{id}/gramage-report/"""
        plan = self.get_object()
        data = MealPlanService.calculate_gramage(plan)
        return Response(data)

    @action(detail=True, methods=["get"], url_path="export-xlsx")
    def export_xlsx(self, request, pk=None):
        """GET /api/admin/meal-plans/{id}/export-xlsx/"""
        plan = self.get_object()
        gramage = MealPlanService.calculate_gramage(plan)
        from ..exporters.meal_plan_xlsx_exporter import MealPlanXLSXExporter

        xlsx_bytes = MealPlanXLSXExporter([gramage]).generate()
        response = HttpResponse(
            xlsx_bytes,
            content_type=_XLSX_CONTENT_TYPE,
        )
        fname = f"jedalnícek_{plan.date}.xlsx"
        response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(fname)}"
        return response

    @action(detail=True, methods=["get"], url_path="export-pdf")
    def export_pdf(self, request, pk=None):
        """GET /api/admin/meal-plans/{id}/export-pdf/"""
        plan = self.get_object()
        gramage = MealPlanService.calculate_gramage(plan)
        from ..exporters.meal_plan_pdf_exporter import MealPlanPDFExporter

        pdf_bytes = MealPlanPDFExporter(gramage).generate()
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        fname = f"jedalnícek_{plan.date}.pdf"
        response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(fname)}"
        return response

    @action(detail=False, methods=["get"], url_path="range-report")
    def range_report(self, request):
        """GET /api/admin/meal-plans/range-report/?from=YYYY-MM-DD&to=YYYY-MM-DD"""
        from_str = request.query_params.get("from")
        to_str = request.query_params.get("to")
        if not from_str or not to_str:
            return Response(
                {"error": "from and to query params required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from_date = parse_date_param(from_str, "from")
        to_date = parse_date_param(to_str, "to")
        data = MealPlanService.calculate_range_gramage(from_date, to_date)
        return Response(data)

    @action(detail=False, methods=["get"], url_path="diet-summary")
    def diet_summary(self, request):
        """
        GET /api/admin/meal-plans/diet-summary/?date=YYYY-MM-DD

        Aggregates DailyOrder records for the given date and returns:
          - diet counts per meal  (how many portions of each special diet per meal)
          - menu variant totals per meal (how many total portions per menu variant)

        Used by the admin report view to show special-diet requirements
        alongside the gramage preview.
        """
        date_str = request.query_params.get("date")
        if not date_str:
            return Response(
                {"error": "date query param required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        date = parse_date_param(date_str)

        from ..models import DailyOrder

        orders = DailyOrder.objects.filter(date=date)

        # {meal: {diet_name: count}}
        diet_by_meal: dict[str, dict[str, int]] = {}
        # {meal: {variant: total_count}}
        menu_totals: dict[str, dict[str, int]] = {}

        for order in orders:
            data = getattr(order, "data", None)
            if not isinstance(data, dict):
                continue

            for category in OrderData(data).iter_categories():
                diet_by_meal.setdefault(category.meal, {})
                menu_totals.setdefault(category.meal, {})

                for variant, count in category.menu_counts.items():
                    if not isinstance(variant, str):
                        continue
                    count_int = safe_count(count)
                    if count_int <= 0:
                        continue
                    menu_totals[category.meal][variant] = (
                        menu_totals[category.meal].get(variant, 0) + count_int
                    )

                for diet_name, count in category.diets.items():
                    if not isinstance(diet_name, str):
                        continue
                    count_int = safe_count(count)
                    if count_int <= 0:
                        continue
                    diet_by_meal[category.meal][diet_name] = (
                        diet_by_meal[category.meal].get(diet_name, 0) + count_int
                    )

        return Response(
            {
                "date": date.isoformat(),
                "diet_by_meal": diet_by_meal,
                "menu_totals": menu_totals,
            }
        )

    @action(detail=False, methods=["get"], url_path="gramage-dashboard")
    def gramage_dashboard(self, request):
        """GET /api/admin/meal-plans/gramage-dashboard/?date=YYYY-MM-DD"""
        date_str = request.query_params.get("date")
        if not date_str:
            return Response(
                {"error": "date required"}, status=status.HTTP_400_BAD_REQUEST
            )
        date = parse_date_param(date_str)
        # Manuálne "Obnoviť" v hlavičke (#573 nadväzne) — cache sa inak
        # prepočíta async na pozadí po každej zmene objednávky (debounce,
        # viď schedule_gramage_dashboard_refresh), ale admin chce vedieť
        # naisto, teraz, bez čakania na debounce okno.
        if _parse_bool_param(request, "refresh", False):
            from ..cache_service import clear_gramage_dashboard_cache

            clear_gramage_dashboard_cache(date.isoformat())
        # Prepínač "Použiť zlúčenie diét" (#568) — default zapnutý (kešovaná
        # vetva). Vypnutý je zámerne nekešovaný, prepočíta sa nanovo — je to
        # zriedkavý explicitný klik, nie niečo, čo treba škálovať.
        merge_diets = _parse_bool_param(request, "merge_diets", True)
        if merge_diets:
            data = _cached_gramage_dashboard_data(date.isoformat())
        else:
            data = MealPlanService.gramage_dashboard(
                date.isoformat(), merge_diets=False
            )
        # Hotový popis tabuľky — obrazovka aj PDF ho renderujú z rovnakého spec-u,
        # aby sa nemali ako rozísť (viď gramage_table_spec).
        from ..exporters.gramage_table_spec import build_table_spec

        sections = request.query_params.getlist("section") or None
        vydaje = request.query_params.getlist("vydaj") or None
        diet_clusters = request.query_params.getlist("diet_cluster") or None
        data["spec"] = build_table_spec(
            data,
            sections=sections,
            vydaje=vydaje,
            include_summary_rows=not _parse_bool_param(request, "expanded", False),
            show_empty=_parse_bool_param(request, "show_empty", True),
            show_cluster_summary=_parse_bool_param(request, "cluster_summary", True),
            diet_clusters=diet_clusters,
        )
        return Response(data)

    @action(detail=False, methods=["get"], url_path="gramage-dashboard-pdf")
    def gramage_dashboard_pdf(self, request):
        """GET /api/admin/meal-plans/gramage-dashboard-pdf/?date=YYYY-MM-DD"""
        date_str = request.query_params.get("date")
        if not date_str:
            return Response(
                {"error": "date required"}, status=status.HTTP_400_BAD_REQUEST
            )
        date = parse_date_param(date_str)
        sections = request.query_params.getlist("section") or None
        vydaje = request.query_params.getlist("vydaj") or None
        diet_clusters = request.query_params.getlist("diet_cluster") or None
        show_empty = _parse_bool_param(request, "show_empty", True)
        show_cluster_summary = _parse_bool_param(request, "cluster_summary", True)
        merge_diets = _parse_bool_param(request, "merge_diets", True)
        # "Nastavenia tabuľky" (2.9.2026): ten istý filter, ktorý admin práve
        # vidí na obrazovke, sa má tlačiť aj do PDF — všetko okrem default
        # stavu preto obchádza uzavretého-dňa cache rovnako ako section/vydaj.
        is_default_view = (
            not sections
            and not vydaje
            and not diet_clusters
            and show_empty
            and show_cluster_summary
            and merge_diets
        )

        # Uzavretý deň má PDF predgenerované a nacachované už pri uzavretí
        # (#528, viď closed_day_views) — ale len pre neprefiltrovaný export,
        # presne taký, aký sa vtedy predgeneroval.
        pdf_bytes = None
        if is_default_view:
            pdf_bytes = get_cached(get_closed_day_pdf_cache_key(date.isoformat()))
        if pdf_bytes is None:
            pdf_bytes = render_gramage_dashboard_pdf(
                date.isoformat(),
                sections=sections,
                vydaje=vydaje,
                show_empty=show_empty,
                show_cluster_summary=show_cluster_summary,
                diet_clusters=diet_clusters,
                merge_diets=merge_diets,
            )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        fname = f"gramaz_{date}.pdf"
        response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(fname)}"
        return response

    @action(detail=False, methods=["get"], url_path="range-export-xlsx")
    def range_export_xlsx(self, request):
        """GET /api/admin/meal-plans/range-export-xlsx/?from=YYYY-MM-DD&to=YYYY-MM-DD"""
        from_str = request.query_params.get("from")
        to_str = request.query_params.get("to")
        if not from_str or not to_str:
            return Response(
                {"error": "from and to query params required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from_date = parse_date_param(from_str, "from")
        to_date = parse_date_param(to_str, "to")
        gramage_list = MealPlanService.calculate_range_gramage(from_date, to_date)
        from ..exporters.meal_plan_xlsx_exporter import MealPlanXLSXExporter

        xlsx_bytes = MealPlanXLSXExporter(gramage_list).generate()
        response = HttpResponse(
            xlsx_bytes,
            content_type=_XLSX_CONTENT_TYPE,
        )
        fname = f"jedalnícek_{from_date}_{to_date}.xlsx"
        response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(fname)}"
        return response


class DietComponentMergeViewSet(viewsets.ViewSet):
    """Klikací zoznam "spolu/zvlášť" (#568) — kuchyňa aj admin.

    Nie `ModelViewSet` — frontend nepozná/nepotrebuje id jednotlivých
    `DietComponentMerge` riadkov, pracuje len s (deň, jedlo, index zložky,
    diéta). `toggle` je preto upsert/delete podľa tejto štvorice, nie CRUD
    nad primárnym kľúčom.
    """

    permission_classes = [IsKuchynaOrAbove]

    @action(detail=False, methods=["get"])
    def board(self, request):
        """GET /api/admin/diet-component-merge/board/?date=YYYY-MM-DD"""
        date_str = request.query_params.get("date")
        if not date_str:
            return Response(
                {"error": "date required"}, status=status.HTTP_400_BAD_REQUEST
            )
        date = parse_date_param(date_str)
        return Response(diet_component_merge_board(date.isoformat()))

    @action(detail=False, methods=["post"])
    def toggle(self, request):
        """POST /api/admin/diet-component-merge/toggle/

        Body: {date, meal, component_index, diet_id, merged, component_label?}.
        `merged=true` vytvorí/aktualizuje riadok "spolu", `merged=false` ho
        zmaže (default "zvlášť" — viď model). Vracia prečerstvený `board`,
        nech frontend nemusí robiť druhý request len na prekreslenie.
        """
        date_str = request.data.get("date")
        meal = request.data.get("meal")
        component_index = request.data.get("component_index")
        diet_id = request.data.get("diet_id")
        if not date_str or not meal or component_index is None or not diet_id:
            return Response(
                {"error": "date, meal, component_index and diet_id required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if meal not in DIET_COMPONENT_MERGE_MEALS:
            return Response(
                {"error": f"unsupported meal: {meal}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        date = parse_date_param(date_str)
        try:
            diet = Diet.objects.get(pk=diet_id)
        except Diet.DoesNotExist:
            return Response(
                {"error": "diet not found"}, status=status.HTTP_404_NOT_FOUND
            )
        try:
            component_index = int(component_index)
        except (TypeError, ValueError):
            return Response(
                {"error": "component_index must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if request.data.get("merged"):
            DietComponentMerge.objects.update_or_create(
                date=date,
                meal=meal,
                component_index=component_index,
                diet=diet,
                defaults={
                    "updated_by": request.user,
                    "component_label": str(request.data.get("component_label") or ""),
                },
            )
        else:
            DietComponentMerge.objects.filter(
                date=date, meal=meal, component_index=component_index, diet=diet
            ).delete()

        return Response(diet_component_merge_board(date.isoformat()))
