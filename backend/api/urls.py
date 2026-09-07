from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .health import health_check
from .views import (
    AdminAutoOrderViewSet,
    AdminCelokViewSet,
    AdminEdupageConnectionViewSet,
    AdminEventLogViewSet,
    AdminFacilityPrevadzkaViewSet,
    AdminHolidayViewSet,
    AdminLogViewSet,
    AdminPrevadzkaClosureViewSet,
    AdminPrevadzkaDeliveryViewSet,
    AdminSendPushView,
    AdminSummaryViewSet,
    AdminUpcomingEventsViewSet,
    AdminUserViewSet,
    ClosedDayViewSet,
    DailyMealPlanViewSet,
    DailyOrderViewSet,
    DeliveryBlockViewSet,
    DeliveryRouteViewSet,
    DietComponentMergeViewSet,
    DietViewSet,
    EmailTokenObtainPairView,
    GlobalSettingsViewSet,
    HolidayListViewSet,
    InboxViewSet,
    LoadingViewSet,
    LogoutView,
    MealTemplateViewSet,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PlannedOrdersViewSet,
    PortionTypeViewSet,
    PrevadzkaClosureListViewSet,
    PrevadzkaViewSet,
    PushSubscribeView,
    SafeTokenRefreshView,
    SectionPermissionViewSet,
    UserProfileViewSet,
    VapidPublicKeyView,
)

router = DefaultRouter()
# NOTE: orders/planned MUST be registered before orders to avoid the
# generic `orders/<pk>` pattern matching "planned" as a PK.
router.register(r"orders/planned", PlannedOrdersViewSet, basename="planned-orders")
router.register(r"orders", DailyOrderViewSet, basename="dailyorder")
router.register(r"prevadzky", PrevadzkaViewSet, basename="prevadzka")
router.register(r"user", UserProfileViewSet, basename="user")
router.register(r"diets", DietViewSet, basename="diet")
router.register(r"admin/celky", AdminCelokViewSet, basename="admin-celok")
router.register(
    r"admin/facility-prevadzky",
    AdminFacilityPrevadzkaViewSet,
    basename="admin-facility-prevadzka",
)
router.register(r"admin/users", AdminUserViewSet, basename="admin-user")
router.register(
    r"admin/section-permissions",
    SectionPermissionViewSet,
    basename="admin-section-permission",
)
router.register(r"admin/logs", AdminLogViewSet, basename="admin-log")
router.register(r"admin/event-logs", AdminEventLogViewSet, basename="admin-event-log")
router.register(
    r"admin/upcoming-events",
    AdminUpcomingEventsViewSet,
    basename="admin-upcoming-event",
)
router.register(
    r"admin/delivery-blocks",
    DeliveryBlockViewSet,
    basename="admin-delivery-block",
)
router.register(
    r"admin/delivery-routes",
    DeliveryRouteViewSet,
    basename="admin-delivery-route",
)
router.register(
    r"admin/prevadzky-delivery",
    AdminPrevadzkaDeliveryViewSet,
    basename="admin-prevadzka-delivery",
)
router.register(r"kuchyna/loading", LoadingViewSet, basename="kuchyna-loading")
router.register(r"admin/summary", AdminSummaryViewSet, basename="adminsummary")
router.register(
    r"admin/global-settings",
    GlobalSettingsViewSet,
    basename="global-settings",
)
router.register(
    r"admin/trigger-auto-orders",
    AdminAutoOrderViewSet,
    basename="trigger-auto-orders",
)
router.register(r"admin/closed-days", ClosedDayViewSet, basename="closed-day")
router.register(r"admin/meal-plans", DailyMealPlanViewSet, basename="meal-plan")
router.register(r"admin/portion-types", PortionTypeViewSet, basename="portion-type")
router.register(r"admin/meal-templates", MealTemplateViewSet, basename="meal-template")
router.register(
    r"admin/diet-component-merge",
    DietComponentMergeViewSet,
    basename="diet-component-merge",
)
router.register(r"meal-plans", DailyMealPlanViewSet, basename="client-meal-plan")
router.register(r"admin/holidays", AdminHolidayViewSet, basename="admin-holiday")
router.register(r"holidays", HolidayListViewSet, basename="holiday")
router.register(
    r"admin/prevadzka-closures",
    AdminPrevadzkaClosureViewSet,
    basename="admin-prevadzka-closure",
)
router.register(
    r"prevadzka-closures", PrevadzkaClosureListViewSet, basename="prevadzka-closure"
)
router.register(r"inbox", InboxViewSet, basename="inbox")
router.register(
    r"admin/edupage-connections",
    AdminEdupageConnectionViewSet,
    basename="admin-edupage-connection",
)
urlpatterns = [
    path("", include(router.urls)),
    path("token/", EmailTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", SafeTokenRefreshView.as_view(), name="token_refresh"),
    path("token/logout/", LogoutView.as_view(), name="token_logout"),
    path("health/", health_check, name="health_check"),
    # Password reset (unauthenticated)
    path(
        "auth/password-reset/",
        PasswordResetRequestView.as_view(),
        name="password_reset_request",
    ),
    path(
        "auth/password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    # Push notifications
    path(
        "push/vapid-public-key/",
        VapidPublicKeyView.as_view(),
        name="vapid_public_key",
    ),
    path(
        "push/subscribe/",
        PushSubscribeView.as_view(),
        name="push_subscribe",
    ),
    path(
        "admin/push/send/",
        AdminSendPushView.as_view(),
        name="admin_push_send",
    ),
]
