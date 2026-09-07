"""
Views package - Re-exports all ViewSets and Views from domain-specific modules.

This allows imports to work the same way as before:
    from api.views import DailyOrderViewSet, ...
"""

# Admin views
from .admin_views import AdminEventLogViewSet, AdminLogViewSet, AdminUserViewSet

# Authentication views
from .auth_views import (
    EmailTokenObtainPairSerializer,
    EmailTokenObtainPairView,
    LogoutView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    SafeTokenRefreshView,
)

# Closed order days
from .closed_day_views import ClosedDayViewSet

# Delivery layout views
from .delivery_views import (
    AdminPrevadzkaDeliveryViewSet,
    DeliveryBlockViewSet,
    DeliveryRouteViewSet,
)

# Diet views
from .diet_views import DietViewSet

# Edupage views
from .edupage_views import AdminEdupageConnectionViewSet

# Facility (celok + prevadzka) admin views
from .facility_views import AdminCelokViewSet, AdminFacilityPrevadzkaViewSet

# Holiday views
from .holiday_views import AdminHolidayViewSet, HolidayListViewSet

# Inbox views
from .inbox_views import InboxViewSet
from .loading_views import LoadingViewSet

# Meal plan views
from .meal_plan_views import (
    DailyMealPlanViewSet,
    DietComponentMergeViewSet,
    MealTemplateViewSet,
    PortionTypeViewSet,
)

# Order views
from .order_views import (
    AdminAutoOrderViewSet,
    DailyOrderViewSet,
    PlannedOrdersViewSet,
    PrevadzkaViewSet,
)

# Voľno prevádzky (#490)
from .prevadzka_closure_views import (
    AdminPrevadzkaClosureViewSet,
    PrevadzkaClosureListViewSet,
)

# Push notification views
from .push_views import AdminSendPushView, PushSubscribeView, VapidPublicKeyView

# Report views
from .report_views import AdminSummaryViewSet
from .section_permission_views import SectionPermissionViewSet

# Settings views
from .settings_views import GlobalSettingsViewSet, UserProfileViewSet

# Upcoming events (naplánované crony)
from .upcoming_events_views import AdminUpcomingEventsViewSet

__all__ = [
    "SectionPermissionViewSet",
    "LoadingViewSet",
    # Authentication
    "EmailTokenObtainPairSerializer",
    # Holidays
    "AdminHolidayViewSet",
    "HolidayListViewSet",
    # Voľno prevádzky
    "AdminPrevadzkaClosureViewSet",
    "PrevadzkaClosureListViewSet",
    "EmailTokenObtainPairView",
    "LogoutView",
    "PasswordResetRequestView",
    "PasswordResetConfirmView",
    "SafeTokenRefreshView",
    # Orders
    "DailyOrderViewSet",
    "PlannedOrdersViewSet",
    "PrevadzkaViewSet",
    "AdminAutoOrderViewSet",
    "ClosedDayViewSet",
    # Admin
    "AdminLogViewSet",
    "AdminEventLogViewSet",
    "AdminUserViewSet",
    # Edupage
    "AdminEdupageConnectionViewSet",
    # Upcoming events
    "AdminUpcomingEventsViewSet",
    # Reports
    "AdminSummaryViewSet",
    # Settings
    "UserProfileViewSet",
    "GlobalSettingsViewSet",
    # Facility (celok + prevadzka)
    "AdminCelokViewSet",
    "AdminFacilityPrevadzkaViewSet",
    # Diet
    "DietViewSet",
    # Delivery layout
    "AdminPrevadzkaDeliveryViewSet",
    "DeliveryBlockViewSet",
    "DeliveryRouteViewSet",
    # Meal plan
    "DailyMealPlanViewSet",
    "PortionTypeViewSet",
    "MealTemplateViewSet",
    "DietComponentMergeViewSet",
    # Push notifications
    "VapidPublicKeyView",
    "PushSubscribeView",
    "AdminSendPushView",
    # Inbox
    "InboxViewSet",
]
