from django.db import transaction
from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .. import sections
from ..models import DeliveryBlock, DeliveryMealType, DeliveryRoute, Prevadzka
from ..permissions import IsAdminOrAbove, SectionAccess
from ..serializers_delivery import (
    DeliveryBlockSerializer,
    DeliveryLayoutSerializer,
    DeliveryPrevadzkaSerializer,
    DeliveryRouteSerializer,
)
from .audit_mixins import AuditedModelViewSetMixin


def _meal_type_from(source, default: str = str(DeliveryMealType.LUNCH)) -> str | None:
    """Vyberie a zvaliduje `meal_type` z query paramov / tela requestu.

    `None` znamená neplatnú hodnotu — volajúci má vrátiť 400. Chýbajúci
    parameter padá na `lunch` (spätná kompatibilita so starými odkazmi bez
    parametra, keď existovala len jedna spoločná trasa).
    """
    meal_type = source.get("meal_type", default)
    if meal_type not in DeliveryMealType.values:
        return None
    return meal_type


@extend_schema_view(
    list=extend_schema(tags=["admin-delivery-layout"]),
    create=extend_schema(tags=["admin-delivery-layout"]),
    retrieve=extend_schema(tags=["admin-delivery-layout"]),
    update=extend_schema(tags=["admin-delivery-layout"]),
    partial_update=extend_schema(tags=["admin-delivery-layout"]),
    destroy=extend_schema(tags=["admin-delivery-layout"]),
    layout=extend_schema(tags=["admin-delivery-layout"]),
    reorder=extend_schema(tags=["admin-delivery-layout"]),
)
class DeliveryBlockViewSet(AuditedModelViewSetMixin, viewsets.ModelViewSet):
    serializer_class = DeliveryBlockSerializer
    permission_classes = [IsAdminOrAbove, SectionAccess]
    section = sections.TRASY

    def get_queryset(self, meal_type: str | None = None):
        qs = DeliveryBlock.objects.all().prefetch_related("routes")
        if meal_type is not None:
            qs = qs.filter(meal_type=meal_type).prefetch_related(
                Prefetch(
                    f"routes__prevadzky_{meal_type}",
                    queryset=Prevadzka.objects.select_related("celok").order_by(
                        f"delivery_sort_order_{meal_type}", "sort_order", "nazov"
                    ),
                ),
            )
        return qs.order_by("sort_order", "name")

    @action(detail=False, methods=["get"], url_path="layout")
    def layout(self, request):
        meal_type = _meal_type_from(request.query_params)
        if meal_type is None:
            return Response(
                {"error": "invalid meal_type"}, status=status.HTTP_400_BAD_REQUEST
            )
        blocks = self.get_queryset(meal_type).filter(is_active=True)
        unassigned = (
            Prevadzka.objects.filter(
                is_active=True, **{f"delivery_route_{meal_type}__isnull": True}
            )
            .select_related("celok")
            .order_by("celok__nazov", "sort_order", "nazov")
        )
        return Response(
            DeliveryLayoutSerializer(
                {"blocks": blocks, "unassigned_prevadzky": unassigned}
            ).data
        )

    @action(detail=False, methods=["post"], url_path="reorder")
    def reorder(self, request):
        meal_type = _meal_type_from(request.data)
        if meal_type is None:
            return Response(
                {"error": "invalid meal_type"}, status=status.HTTP_400_BAD_REQUEST
            )
        blocks = request.data.get("blocks", [])
        if not isinstance(blocks, list):
            return Response(
                {"error": "blocks must be a list"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        route_field = f"delivery_route_{meal_type}_id"
        sort_field = f"delivery_sort_order_{meal_type}"

        with transaction.atomic():
            for block_index, block_payload in enumerate(blocks, start=1):
                block_id = block_payload.get("id")
                if block_id is None:
                    continue
                DeliveryBlock.objects.filter(pk=block_id, meal_type=meal_type).update(
                    sort_order=block_payload.get("sort_order", block_index)
                )

                routes = block_payload.get("routes", [])
                if not isinstance(routes, list):
                    continue
                for route_index, route_payload in enumerate(routes, start=1):
                    route_id = route_payload.get("id")
                    if route_id is None:
                        continue
                    DeliveryRoute.objects.filter(
                        pk=route_id, block__meal_type=meal_type
                    ).update(
                        block_id=block_id,
                        sort_order=route_payload.get("sort_order", route_index),
                    )

                    prevadzky = route_payload.get("prevadzky", [])
                    if not isinstance(prevadzky, list):
                        continue
                    for prevadzka_index, prevadzka_payload in enumerate(
                        prevadzky, start=1
                    ):
                        prevadzka_id = prevadzka_payload.get("id")
                        if prevadzka_id is None:
                            continue
                        Prevadzka.objects.filter(pk=prevadzka_id).update(
                            **{
                                route_field: route_id,
                                sort_field: prevadzka_payload.get(
                                    "delivery_sort_order", prevadzka_index
                                ),
                            }
                        )

            unassigned = request.data.get("unassigned_prevadzky", [])
            if isinstance(unassigned, list):
                for prevadzka_payload in unassigned:
                    prevadzka_id = prevadzka_payload.get("id")
                    if prevadzka_id is not None:
                        Prevadzka.objects.filter(pk=prevadzka_id).update(
                            **{route_field: None, sort_field: 0}
                        )

        return self.layout(request)


@extend_schema_view(
    list=extend_schema(tags=["admin-delivery-layout"]),
    create=extend_schema(tags=["admin-delivery-layout"]),
    retrieve=extend_schema(tags=["admin-delivery-layout"]),
    update=extend_schema(tags=["admin-delivery-layout"]),
    partial_update=extend_schema(tags=["admin-delivery-layout"]),
    destroy=extend_schema(tags=["admin-delivery-layout"]),
)
class DeliveryRouteViewSet(AuditedModelViewSetMixin, viewsets.ModelViewSet):
    queryset = DeliveryRoute.objects.select_related("block")
    serializer_class = DeliveryRouteSerializer
    permission_classes = [IsAdminOrAbove, SectionAccess]
    section = sections.TRASY

    def get_queryset(self):
        qs = super().get_queryset()
        meal_type = self.request.query_params.get("meal_type")
        if meal_type:
            qs = qs.filter(block__meal_type=meal_type)
        return qs


@extend_schema_view(
    list=extend_schema(tags=["admin-delivery-layout"]),
    retrieve=extend_schema(tags=["admin-delivery-layout"]),
    update=extend_schema(tags=["admin-delivery-layout"]),
    partial_update=extend_schema(tags=["admin-delivery-layout"]),
)
class AdminPrevadzkaDeliveryViewSet(AuditedModelViewSetMixin, viewsets.ModelViewSet):
    queryset = Prevadzka.objects.select_related(
        "celok",
        "delivery_route_breakfast",
        "delivery_route_lunch",
        "delivery_route_olovrant",
    ).order_by("celok__nazov", "sort_order", "nazov")
    serializer_class = DeliveryPrevadzkaSerializer
    permission_classes = [IsAdminOrAbove, SectionAccess]
    section = sections.TRASY
    http_method_names = ["get", "patch", "put", "head", "options"]
