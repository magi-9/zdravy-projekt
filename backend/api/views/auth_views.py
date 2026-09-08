import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import Throttled
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from api.management.commands.init_roles import DEMO_ADMIN_EMAIL, DEMO_OPERATION_EMAIL

from ..exceptions import InvalidCredentialsError, MissingRequiredFieldError
from ..metrics import login_attempts_total
from ..roles import is_admin_or_above, role_of
from ..throttles import LoginRateThrottle

logger = logging.getLogger(__name__)

# Differentiated refresh token lifetimes by role.
# Admins: 1 day — they use the web admin UI, not the PWA; short lifetime appropriate
#   given they have access to all client data.
# Clients: 30 days — they may open the app as infrequently as every two weeks;
#   rotation resets the clock on each visit so they're only logged out after 30 days
#   of complete inactivity.
_ADMIN_REFRESH_LIFETIME = timedelta(days=1)
_CLIENT_REFRESH_LIFETIME = timedelta(days=30)

_COOKIE_NAME = settings.REFRESH_TOKEN_COOKIE_NAME
_COOKIE_PATH = settings.REFRESH_TOKEN_COOKIE_PATH
PASSWORD_RESET_CONFIRM_ERROR = "Neplatný alebo expirovaný odkaz na obnovu hesla."


def _set_refresh_cookie(response: Response, refresh_str: str, max_age: int) -> None:
    response.set_cookie(
        _COOKIE_NAME,
        refresh_str,
        max_age=max_age,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Lax",
        path=_COOKIE_PATH,
    )


def _delete_refresh_cookie(response: Response) -> None:
    response.delete_cookie(_COOKIE_NAME, path=_COOKIE_PATH)


def _refresh_cookie_candidates(request) -> list[str]:
    raw_cookie = request.META.get("HTTP_COOKIE", "")
    values: list[str] = []
    for part in raw_cookie.split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == _COOKIE_NAME and value:
            values.append(value)

    fallback = request.COOKIES.get(_COOKIE_NAME)
    if fallback:
        values.append(fallback)

    unique_values = []
    for value in values:
        if value not in unique_values:
            unique_values.append(value)
    return unique_values


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """JWT token serializer that authenticates via email instead of username."""

    username_field = "email"

    @staticmethod
    def _sync_dev_demo_user(email: str) -> None:
        if not settings.DEBUG:
            return

        if email not in {DEMO_ADMIN_EMAIL, DEMO_OPERATION_EMAIL}:
            return

        call_command("init_roles", verbosity=0)

    @staticmethod
    def _find_user_for_login(email: str, password: str) -> User:
        """
        Return the active user whose password matches email, or raise
        InvalidCredentialsError.

        Both wrong-password and inactive-account cases raise the same error
        to prevent user enumeration (consistent with password_reset_service.py).
        Materialising the queryset once avoids the 3-query pattern that
        existed when .exists(), .count(), and iteration hit the DB separately.
        """
        EmailTokenObtainPairSerializer._sync_dev_demo_user(email)

        candidates = list(
            User.objects.filter(email__iexact=email).order_by("-is_active", "id")
        )
        if not candidates:
            raise InvalidCredentialsError()

        if len(candidates) > 1:
            logger.error(
                "Duplicate user emails detected for %s (count=%s)",
                email,
                len(candidates),
            )

        for candidate in candidates:
            if candidate.check_password(password) and candidate.is_active:
                return candidate

        raise InvalidCredentialsError()

    def validate(self, attrs):
        """
        Authenticate by email + password and return JWT tokens.

        The refresh token is NOT included in the returned dict — the view pops
        it out and sets it as an httpOnly cookie.  The ``_refresh`` attribute is
        set on the serializer so the view can compute the correct max_age.
        """
        email = attrs.get("email", "").strip().lower()
        password = attrs.get("password", "")

        if not email:
            raise InvalidCredentialsError()

        user = self._find_user_for_login(email=email, password=password)

        from ..cached_settings_service import get_global_settings

        if get_global_settings().maintenance_is_active() and not is_admin_or_above(
            user
        ):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Aplikácia je počas údržby dočasne nedostupná.")

        lifetime = (
            _ADMIN_REFRESH_LIFETIME if user.is_staff else _CLIENT_REFRESH_LIFETIME
        )
        refresh = RefreshToken.for_user(user)
        refresh.set_exp(lifetime=lifetime)
        # Embed is_staff so rotation can re-apply the correct lifetime without a
        # DB query (avoids both a per-rotation SELECT and the exception-fallback
        # path that would silently promote an admin to a 30-day token).
        refresh["is_staff"] = user.is_staff
        # `role` je len informatívny claim; autorizácia sa vždy rozhoduje z DB.
        # Tokeny vydané pred #482 ho nemajú, preto ho rotácia nikdy nesmie
        # vyžadovať — inak by deploy odhlásil každého prihláseného admina.
        refresh["role"] = role_of(user)

        # Store on the instance so the view can read the lifetime without re-parsing
        self._refresh = refresh

        return {
            "refresh": str(refresh),  # view pops this before returning to client
            "access": str(refresh.access_token),
        }


@extend_schema(tags=["auth"])
class EmailTokenObtainPairView(TokenObtainPairView):
    """JWT login view. Returns access token in body; sets refresh token as httpOnly cookie."""

    serializer_class = EmailTokenObtainPairSerializer
    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        login_attempts_total.labels(result="success", reason="success").inc()

        refresh_str: str = serializer.validated_data["refresh"]
        access_str: str = serializer.validated_data["access"]
        refresh_obj: RefreshToken = serializer._refresh

        exp = refresh_obj.payload["exp"]
        iat = refresh_obj.payload["iat"]
        max_age = int(exp - iat)

        response = Response({"access": access_str}, status=status.HTTP_200_OK)
        _set_refresh_cookie(response, refresh_str, max_age=max_age)
        return response

    def handle_exception(self, exc):
        # Throttling (LoginRateThrottle) is raised in dispatch()'s initial()
        # step, before post() runs, so it must be counted here rather than in
        # post()'s body. Runs exactly once per request either way — dispatch()
        # calls handle_exception() for both a throttle-time exception and one
        # re-raised out of post() — so counting only here avoids double-counting.
        reason = (
            "throttled"
            if isinstance(exc, Throttled)
            else getattr(exc, "error_code", "validation_error")
        )
        login_attempts_total.labels(result="failure", reason=reason).inc()
        return super().handle_exception(exc)


@extend_schema(tags=["auth"])
class SafeTokenRefreshView(TokenRefreshView):
    """
    Token refresh view.

    Reads the refresh token from the httpOnly cookie (not the request body).
    Returns the new access token in the body and rotates the refresh cookie.
    """

    def post(self, request, *args, **kwargs):
        refresh_candidates = _refresh_cookie_candidates(request)
        if not refresh_candidates:
            raise InvalidToken("Refresh token nenájdený.")

        last_error: Exception | None = None
        serializer = None
        for refresh_str in refresh_candidates:
            data = (
                request.data.copy()
                if hasattr(request.data, "copy")
                else dict(request.data)
            )
            data["refresh"] = refresh_str
            candidate_serializer = self.get_serializer(data=data)
            try:
                candidate_serializer.is_valid(raise_exception=True)
            except (InvalidToken, TokenError, User.DoesNotExist) as exc:
                last_error = exc
                continue
            serializer = candidate_serializer
            break

        if serializer is None:
            if isinstance(last_error, (InvalidToken, TokenError)):
                raise InvalidToken(last_error.args[0]) from last_error
            raise InvalidToken("Token neplatný alebo expirovaný.") from last_error

        new_access: str = serializer.validated_data["access"]
        # ROTATE_REFRESH_TOKENS=True → the serializer returns a new refresh token.
        # SimpleJWT's rotation calls set_exp() without a lifetime argument so it
        # always resets to the global REFRESH_TOKEN_LIFETIME (30 days).  Read the
        # is_staff claim we embedded at login to re-apply the correct lifetime
        # without a DB query — no exception-fallback path needed.
        new_refresh: str | None = serializer.validated_data.get("refresh")

        response = Response({"access": new_access}, status=status.HTTP_200_OK)

        if new_refresh:
            obj = RefreshToken(new_refresh)  # type: ignore[arg-type]
            lifetime = (
                _ADMIN_REFRESH_LIFETIME
                if obj.payload.get("is_staff")
                else _CLIENT_REFRESH_LIFETIME
            )
            obj.set_exp(lifetime=lifetime)
            new_refresh = str(obj)
            _set_refresh_cookie(
                response, new_refresh, max_age=int(lifetime.total_seconds())
            )

        return response


@extend_schema(tags=["auth"])
class LogoutView(APIView):
    """
    POST /api/token/logout/

    Blacklists the refresh token from the httpOnly cookie and clears it.
    Requires a valid access token in the Authorization header.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_candidates = _refresh_cookie_candidates(request)
        if refresh_candidates:
            blacklisted = False
            try:
                for refresh_str in refresh_candidates:
                    try:
                        token = RefreshToken(refresh_str)  # type: ignore[arg-type]
                        token.blacklist()
                        blacklisted = True
                    except TokenError:
                        continue
            except Exception:
                # DB failures during logout should remain visible in monitoring.
                logger.warning(
                    "Could not blacklist refresh token on logout",
                    exc_info=True,
                )
            if not blacklisted:
                logger.info("Logout received only invalid refresh token cookies")

        response = Response(
            {"detail": "Odhlásenie bolo úspešné."}, status=status.HTTP_200_OK
        )
        _delete_refresh_cookie(response)
        return response


@extend_schema(tags=["auth"])
class PasswordResetRequestView(APIView):
    """
    POST /api/auth/password-reset/
    Body: {"email": "user@example.com"}

    Initiates a password-reset flow.
    Always returns HTTP 200 to avoid leaking whether an email is registered.
    Returns HTTP 429 with a retry_after field when rate-limited.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from ..exceptions import RateLimitExceeded, TooSoonError
        from ..password_reset_service import request_password_reset

        email = request.data.get("email", "").strip()
        if not email:
            raise MissingRequiredFieldError("email", detail="Pole e-mail je povinné.")

        try:
            request_password_reset(email)
        except (RateLimitExceeded, TooSoonError):
            raise
        except Exception:
            logger.exception(
                "Unexpected error during password reset request for %s", email
            )
            return Response(
                {
                    "detail": (
                        "Ak je táto e-mailová adresa registrovaná, "
                        "bol na ňu odoslaný odkaz na obnovu hesla."
                    )
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "detail": (
                    "Ak je táto e-mailová adresa registrovaná, "
                    "bol na ňu odoslaný odkaz na obnovu hesla."
                )
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(tags=["auth"])
class PasswordResetConfirmView(APIView):
    """
    POST /api/auth/password-reset/confirm/
    Body: {"token": "<reset_token>", "new_password": "<new_password>"}

    Validates the token, sets the new password, and invalidates all outstanding
    JWT refresh tokens for the user so existing sessions are terminated.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from ..password_reset_service import confirm_password_reset

        token = request.data.get("token", "").strip()
        new_password = request.data.get("new_password", "")

        if not token:
            raise MissingRequiredFieldError("token", detail="Token je povinný.")
        if not new_password:
            raise MissingRequiredFieldError(
                "new_password", detail="Nové heslo je povinné."
            )

        try:
            confirm_password_reset(token=token, new_password=new_password)
        except ValueError as exc:
            logger.info("Password reset confirmation failed: %s", exc)
            # `confirm_password_reset` already crafts a message that is safe to
            # show (does not leak whether an account exists) but distinguishes
            # *why* it failed — used / expired / invalid — instead of a single
            # generic string for every case (issue #461).
            #
            # `code` ide von preto, aby sa frontend nemusel rozhodovať podľa textu
            # hlášky: pri už uplatnenom odkaze ponúkne prihlásenie namiesto toho,
            # aby používateľa nechal na slepej ulici.
            return Response(
                {
                    "detail": str(exc) or PASSWORD_RESET_CONFIRM_ERROR,
                    "code": getattr(exc, "code", "invalid"),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"detail": "Heslo bolo úspešne zmenené. Môžete sa prihlásiť."},
            status=status.HTTP_200_OK,
        )
