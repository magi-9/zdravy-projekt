import datetime
from copy import deepcopy
from typing import Optional

from django.contrib.auth.models import User
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import pagination, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from ..exceptions import ClientOnlyError, ClosedDayOrderModificationError
from ..models import ClosedDay, DailyOrder, EventLog
from ..permissions import IsAdminOrAbove
from ..roles import is_admin_or_above, is_klient
from ..serializers import DailyOrderSerializer, PrevadzkaSerializer
from ..services import OrderService
from ..services.event_log_service import build_nested_dict_diff, log_event
from ..services.prevadzka_service import dostupne_prevadzky
from ..throttles import OrderSubmitRateThrottle


class DailyOrderPagination(pagination.PageNumberPagination):
    """Rovnaké defaulty ako globálne (`PAGE_SIZE=20`), len navyše dovolí
    volajúcemu vypýtať si menšiu stránku cez `?page_size=` — ClientDetail
    dashboard tak môže natiahnuť len pár posledných objednávok bez
    zbytočného payloadu celej histórie."""

    page_size_query_param = "page_size"
    max_page_size = 100


@extend_schema_view(
    list=extend_schema(tags=["orders"]),
    retrieve=extend_schema(tags=["orders"]),
    create=extend_schema(tags=["orders"]),
    update=extend_schema(tags=["orders"]),
    partial_update=extend_schema(tags=["orders"]),
    destroy=extend_schema(tags=["orders"]),
    by_date=extend_schema(tags=["orders"]),
)
class DailyOrderViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing daily orders.
    """

    serializer_class = DailyOrderSerializer
    pagination_class = DailyOrderPagination
    # Authenticated users only
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self) -> QuerySet[DailyOrder]:
        """
        Get filtered DailyOrder queryset for the current request user.

        Staff users may optionally filter by another user's ID via the
        "user_id" query parameter; otherwise, only the requesting user's
        orders are returned.

        Query Optimization: No select_related/prefetch_related is needed here
        because DailyOrderSerializer only accesses direct DailyOrder fields
        (id, date, status, data, is_auto, updated_at) and does not dereference
        any related objects like user or settings. As a result, the base
        queryset is already optimized and query count remains constant
        regardless of the number of orders returned.
        """
        queryset = DailyOrder.objects.all()
        user = self.request.user

        prevadzka_id = self.request.query_params.get("prevadzka")
        if is_admin_or_above(user):
            user_id = self.request.query_params.get("user_id")
            if user_id:
                try:
                    user_id_int = int(user_id)
                except (TypeError, ValueError):
                    raise ValidationError({"user_id": "Must be an integer."})
                queryset = queryset.filter(user_id=user_id_int)
            elif prevadzka_id:
                # Admin detail prevádzky je identifikovaný prevádzkou, nie loginom.
                # Bez tohto by sa najprv filtrovalo na objednávky admin usera a
                # detail prevádzky bez loginu by vždy vyzeral prázdny.
                pass
            else:
                # If no user_id is provided, return only the staff user's own orders
                # to prevent returning ALL orders by default (which breaks by_date logic).
                queryset = queryset.filter(user=user)
        else:
            # Objednávka patrí prevádzke, `user` je iba audit toho, kto ju zadal.
            # Viac loginov pod jedným celkom má vidieť rovnakú objednávku prevádzky.
            queryset = queryset.filter(prevadzka__in=dostupne_prevadzky(user))

        if prevadzka_id:
            try:
                prevadzka_id_int = int(prevadzka_id)
            except (TypeError, ValueError):
                raise ValidationError({"prevadzka": "Must be an integer."})
            if (
                not is_admin_or_above(user)
                and not dostupne_prevadzky(user).filter(pk=prevadzka_id_int).exists()
            ):
                raise ValidationError(
                    {"prevadzka": "Prevádzka nepatrí tomuto prihláseniu."}
                )
            queryset = queryset.filter(prevadzka_id=prevadzka_id_int)

        # História objednávok v admin detaile prevádzky sa listuje po
        # stránkach (najnovšie prvé) — bez explicitného poradia by DRV
        # pagination vrátila riadky v poradí DB (id), nie podľa dátumu.
        return queryset.order_by("-date")

    def get_throttles(self):
        if self.action == "create":
            return [OrderSubmitRateThrottle()]
        return super().get_throttles()

    def perform_create(self, serializer: DailyOrderSerializer) -> None:
        """
        Attach the requesting user to the order.

        Staff users may create orders on behalf of a client by supplying a
        ``user_id`` query parameter.  The target user must exist and must not
        be a staff member.

        Raises:
            ClientOnlyError: When a staff member attempts to create an order
                without specifying a ``user_id``.
            ValidationError: When ``user_id`` refers to another staff account.
        """
        if is_admin_or_above(self.request.user):
            user_id = self.request.query_params.get("user_id")
            if not user_id:
                if "prevadzka" in serializer.validated_data:
                    target_user = self.request.user
                    order = serializer.save(user=target_user)
                else:
                    raise ClientOnlyError()
            else:
                try:
                    user_id_int = int(user_id)
                except (TypeError, ValueError):
                    raise ValidationError({"user_id": "Must be an integer."})
                target_user = get_object_or_404(User, pk=user_id_int)
                if not is_klient(target_user):
                    raise ValidationError(
                        {
                            "user_id": "Objednávky sa dajú vytvárať len klientskym loginom."
                        }
                    )
                order = serializer.save(user=target_user)
        else:
            # `create()` je upsert (viď `DailyOrderSerializer.create`) — bežné
            # klientske podanie objednávky ide výhradne cez POST sem, teda aj
            # úpravy aj mazanie (status="draft") toho istého (prevadzka, date)
            # riadku. `_audit_event` na vrátenej inštancii hovorí, čo z toho
            # sa reálne stalo.
            target_user = self.request.user
            order = serializer.save(user=self.request.user)
        self._log_order_audit(
            order=order, actor=self.request.user, target_user=target_user
        )

    def perform_update(self, serializer: DailyOrderSerializer) -> None:
        previous_data = deepcopy(serializer.instance.data or {})
        target_user = serializer.instance.user
        order = serializer.save()
        order._audit_event = "update"
        # Serializer načítava riadok pod lockom; jeho snapshot je jediný
        # správny základ auditu pri paralelnom PATCHi.
        order._audit_previous_data = getattr(
            order, "_audit_previous_data", previous_data
        )
        self._log_order_audit(
            order=order, actor=self.request.user, target_user=target_user
        )

    def perform_destroy(self, instance: DailyOrder) -> None:
        if ClosedDay.objects.filter(date=instance.date).exists():
            raise ClosedDayOrderModificationError()
        order_id = instance.pk
        order_date = instance.date
        order_prevadzka = instance.prevadzka
        target_user = instance.user
        previous_data = deepcopy(instance.data or {})
        instance.delete()
        placeholder = DailyOrder(
            id=order_id, prevadzka=order_prevadzka, date=order_date, data={}
        )
        placeholder._audit_event = "delete"
        placeholder._audit_previous_data = previous_data
        self._log_order_audit(
            order=placeholder, actor=self.request.user, target_user=target_user
        )

    _ORDER_AUDIT_EVENT_TYPES = {
        "create": EventLog.EventType.ORDER_ADMIN_CREATE,
        "update": EventLog.EventType.ORDER_ADMIN_UPDATE,
        "delete": EventLog.EventType.ORDER_ADMIN_DELETE,
    }
    _ORDER_AUDIT_VERBS = {
        "create": "zadal(a)",
        "update": "upravil(a)",
        "delete": "vymazal(a)",
    }

    def _log_order_audit(
        self, *, order: DailyOrder, actor: User, target_user: Optional[User]
    ) -> None:
        """Zapíše create/update/delete objednávky do EventLogu.

        `_audit_event`/`_audit_previous_data` nastavuje
        `DailyOrderSerializer.create()`/`update()`, lebo len tam vieme, či POST
        na (prevadzka, date) v skutočnosti prepísal existujúci riadok, alebo
        (pri `status="draft"`) rovno zmazal — view samotný to z výsledku
        nevie odlíšiť. Chýbajúci tag (`None`) znamená "nič sa reálne nestalo"
        (napr. draft na už prázdnu objednávku) — vtedy sa neloguje nič.
        """
        audit_event = getattr(order, "_audit_event", None)
        if audit_event is None:
            return
        previous_data = getattr(order, "_audit_previous_data", {}) or {}
        new_data = {} if audit_event == "delete" else (order.data or {})
        if previous_data == new_data:
            return  # žiadna reálna zmena dát — nič nezapisovať
        changed_meals = [
            meal
            for meal in DailyOrderSerializer.MEAL_FIELD_CONFIG
            if previous_data.get(meal, {}) != new_data.get(meal, {})
        ]
        target_label = target_user.email if target_user else str(order.prevadzka)
        is_on_behalf = target_user is not None and target_user.pk != actor.pk
        who = (
            f"Admin {actor.email} {self._ORDER_AUDIT_VERBS[audit_event]} objednávku pre {target_label}"
            if is_on_behalf
            else f"{actor.email} {self._ORDER_AUDIT_VERBS[audit_event]} objednávku"
        )
        log_event(
            self._ORDER_AUDIT_EVENT_TYPES[audit_event],
            actor=actor,
            target_user=target_user,
            prevadzka=order.prevadzka,
            summary=f"{who} (prevádzka: {order.prevadzka}) na {order.date}.",
            payload={
                "order_id": order.pk,
                "date": str(order.date),
                "prevadzka_id": order.prevadzka_id,
                "prevadzka_nazov": str(order.prevadzka) if order.prevadzka else None,
                "changed_meals": changed_meals,
                "changes": build_nested_dict_diff(previous_data, new_data),
                "meals": {meal: new_data.get(meal, {}) for meal in changed_meals},
            },
        )

    @action(detail=False, methods=["get"], url_path="by-date/(?P<date>[^/.]+)")
    def by_date(self, request: Request, date: Optional[str] = None) -> Response:
        """
        Return the order for a specific date, or ``{"data": {}}`` when none exists.

        Args:
            date: ISO-8601 date string (``YYYY-MM-DD``) captured from the URL.
        """
        try:
            order = self.get_queryset().get(date=date)
            serializer = self.get_serializer(order)
            return Response(serializer.data)
        except DailyOrder.DoesNotExist:
            return Response(
                {"data": {}}, status=status.HTTP_200_OK
            )  # Return empty struct if not found
        except DailyOrder.MultipleObjectsReturned:
            return Response(
                {
                    "prevadzka": (
                        "Prihlásenie má viac objednávok pre tento deň. "
                        "Pošlite ?prevadzka=<id>."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


@extend_schema(tags=["orders"])
class PlannedOrdersViewSet(viewsets.ViewSet):
    """
    Returns the 5 upcoming workdays with order status for the logged-in client.
    GET /api/orders/planned/
    """

    permission_classes = [permissions.IsAuthenticated]

    def list(self, request: Request) -> Response:
        """Get planned orders for the next 5 workdays via OrderService."""
        result = OrderService.get_planned_orders(request.user)
        return Response(result)

    @action(detail=False, methods=["get"], url_path="monthly-summary")
    def monthly_summary(self, request: Request) -> Response:
        """GET /api/orders/planned/monthly-summary/?year=YYYY&month=M."""
        today = timezone.localdate()
        try:
            year = int(request.query_params.get("year", today.year))
            month = int(request.query_params.get("month", today.month))
            if month < 1 or month > 12:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"error": "Invalid year/month query params."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(OrderService.monthly_summary(request.user, year, month))


@extend_schema(tags=["admin"])
class AdminAutoOrderViewSet(viewsets.ViewSet):
    """
    Admin endpoint to manually trigger auto-order for a given date.
    POST /api/admin/trigger-auto-orders/  { "date": "YYYY-MM-DD" }  (date optional)
    """

    permission_classes = [IsAdminOrAbove]

    def create(self, request: Request) -> Response:
        date_str = request.data.get("date")
        target_date: Optional[datetime.date] = None
        if date_str:
            try:
                target_date = datetime.date.fromisoformat(date_str)
            except ValueError:
                return Response(
                    {"error": "Invalid date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        from ..services import apply_auto_orders

        result = apply_auto_orders(target_date)
        log_event(
            EventLog.EventType.AUTO_ORDER_RUN,
            actor=request.user,
            summary=f"Admin spustil auto-objednávky na {result['date']}.",
            payload={
                "created_count": len(result["created"]),
                "skipped_count": result["skipped"],
                "date": result["date"],
            },
        )
        return Response(result, status=status.HTTP_200_OK)


class PrevadzkaViewSet(viewsets.ReadOnlyModelViewSet):
    """Prevádzky, za ktoré prihlásený klient smie objednávať.

    Frontend podľa počtu rozhodne: jedna → objednáva rovno (ako doteraz),
    viac → najprv nechá vybrať prevádzku.
    """

    serializer_class = PrevadzkaSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self) -> QuerySet:
        return (
            dostupne_prevadzky(self.request.user)
            .select_related("celok")
            .prefetch_related("visible_diets", "visible_portion_types")
        )
