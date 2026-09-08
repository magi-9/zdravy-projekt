"""Server-side protection for scheduled client maintenance windows."""

from django.contrib.auth import get_user_model
from django.http import JsonResponse
from rest_framework_simplejwt.tokens import AccessToken

from .cached_settings_service import get_global_settings
from .roles import is_admin_or_above


class MaintenanceModeMiddleware:
    """Reject client JWT requests while maintenance is active.

    This sits before DRF so an already-open client PWA cannot keep submitting
    orders by calling the API directly. The public settings endpoint stays
    readable because the maintenance screen needs its end time.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith("/api/") or request.path == "/api/health/":
            return self.get_response(request)

        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return self.get_response(request)

        try:
            token = AccessToken(authorization.removeprefix("Bearer "))
            user = (
                get_user_model()
                .objects.select_related("profile")
                .get(id=token["user_id"], is_active=True)
            )
            maintenance_active = get_global_settings().maintenance_is_active()
        except Exception:  # Authentication remains DRF's responsibility.
            return self.get_response(request)

        if maintenance_active and not is_admin_or_above(user):
            return JsonResponse(
                {"detail": "Aplikácia je počas údržby dočasne nedostupná."},
                status=503,
            )
        return self.get_response(request)
