"""
Django base settings for all environments.
"""

import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse, urlunparse


def env(name, default=None):
    """Read env var directly or from <NAME>_FILE for Docker Swarm secrets."""
    value = os.environ.get(name)
    if value not in (None, ""):
        return value

    file_path = os.environ.get(f"{name}_FILE")
    if file_path:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError as exc:
            raise RuntimeError(
                f"Failed to read secret file for {name}: {file_path}"
            ) from exc

    return default


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env(
    "DJANGO_SECRET_KEY", "django-insecure-development-key-change-in-production"
)


def validate_deployed_secret_key(secret_key: str, environment: str) -> None:
    """Fail fast when deployed environments use an unsafe Django/JWT HMAC key."""
    stripped = secret_key.strip()
    if not stripped or stripped.startswith("django-insecure"):
        raise RuntimeError(
            "DJANGO_SECRET_KEY env var is missing or insecure. "
            f"Set a strong secret key before running in {environment}."
        )

    key_length = len(secret_key.encode("utf-8"))
    if key_length < 32:
        raise RuntimeError(
            "DJANGO_SECRET_KEY must be at least 32 bytes for JWT HS256 signing "
            f"({key_length} bytes configured). Generate a new secret key before "
            f"running in {environment}."
        )


# Application definition
INSTALLED_APPS = [
    # Prometheus metrics monitoring
    "django_prometheus",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party apps
    "rest_framework",
    "corsheaders",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_celery_beat",
    # Local apps
    "api",
    # API documentation
    "drf_spectacular",
]

MIDDLEWARE = [
    # Prometheus metrics - must be first to measure all requests
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "api.middleware.NoCacheMiddleware",
    "api.middleware.UnauthorizedAccessRedirectMiddleware",
    "api.maintenance.MaintenanceModeMiddleware",
    # Prometheus metrics - must be last to complete measurement
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "app.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "app.wsgi.application"

# Database
DATABASES = {
    "default": {
        "ENGINE": "django_prometheus.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "zdravy_projekt_db"),
        "USER": os.environ.get("POSTGRES_USER", "postgres"),
        "PASSWORD": env("POSTGRES_PASSWORD", "postgres"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": int(os.environ.get("CONN_MAX_AGE", 600)),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation."
        "UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Bratislava"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"

# Media files
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Redis
def _redis_url_with_db(url: str, db: int) -> str:
    """Return a Redis URL targeting a specific logical database."""
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path=f"/{db}"))


REDIS_URL = os.environ.get("REDIS_URL")
REDIS_CACHE_URL = _redis_url_with_db(REDIS_URL, 1) if REDIS_URL else None
REDIS_CELERY_URL = _redis_url_with_db(REDIS_URL, 0) if REDIS_URL else None

# Cache – Redis when REDIS_URL is set, LocMem for development
if REDIS_CACHE_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_prometheus.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_CACHE_URL,
            "KEY_PREFIX": "zdravy_projekt",
            "TIMEOUT": 300,  # Default 5-minute timeout
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "CONNECTION_POOL_CLASS": "redis.connection.BlockingConnectionPool",
                "CONNECTION_POOL_KWARGS": {
                    "max_connections": 50,
                    "timeout": 20,  # Socket connect timeout: 20s
                },
                "SOCKET_CONNECT_TIMEOUT": 20,  # Connection timeout
                "SOCKET_TIMEOUT": 20,  # Read/write timeout
                "RETRY_ON_TIMEOUT": True,
                "HEALTH_CHECK_INTERVAL": 30,  # Periodic connection check
            },
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django_prometheus.cache.backends.locmem.LocMemCache",
            "KEY_PREFIX": "zdravy_projekt",
            "TIMEOUT": 300,  # Default 5-minute timeout
        }
    }

# Celery – with Redis connection pooling, extended timeouts for Docker Swarm DNS
# On Docker Swarm, DNS resolution can be slow due to overlay network delays.
CELERY_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL", REDIS_CELERY_URL or "redis://localhost:6379/0"
)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Europe/Bratislava"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Startup retry logic: keep retrying indefinitely on startup until Redis is available
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_RETRY = True
CELERY_BROKER_CONNECTION_MAX_RETRIES = None  # Infinite retries on startup

# Transport options with extended timeouts for slow Docker Swarm DNS
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "socket_connect_timeout": 30,  # Increased for Docker Swarm DNS delays
    "socket_timeout": 30,  # Read/write timeout
    "max_retries": 100,  # Retry up to 100 times before giving up
    "interval_start": 1,  # Start retry backoff at 1s
    "interval_step": 1,  # Increase by 1s each retry
    "interval_max": 10,  # Cap retry interval at 10s
}

# Result backend with same timeout settings
CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = {
    "socket_connect_timeout": 30,
    "socket_timeout": 30,
    "master_name": "mymaster",
}

# Frontend URL – used for building links inside transactional emails.
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

# Push Notifications (VAPID)
# Generate keys with: python manage.py generate_vapid_keys
VAPID_PUBLIC_KEY = env("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = env("VAPID_PRIVATE_KEY", "")
VAPID_ADMIN_EMAIL = env("VAPID_ADMIN_EMAIL", "admin@example.com")

# JWT – longer lifetimes so the PWA stays logged in across background/resume cycles.
# Access token: 30 min (default 5 min was too short; phones throttle background
#   refresh and the token expired before the app could refresh it).
# Refresh token: default 30 days (overridden per user at login — admins get 1 day,
#   clients get 30 days since they may open the app as infrequently as every 2 weeks;
#   rotation resets the clock on each active visit so clients are never logged out
#   while actively using the app).
#
# Refresh tokens are stored in an httpOnly, Secure, SameSite=Lax cookie — never
# accessible to JavaScript, eliminating the XSS exfiltration path.
# ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION give server-side revocation:
# each refresh call issues a new token and blacklists the old one so a stolen token
# becomes useless after the legitimate client refreshes once.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=30
    ),  # default; overridden per user in login view
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

# httpOnly cookie used to transport the refresh token.
REFRESH_TOKEN_COOKIE_NAME = "refresh_token"
# Restrict the cookie to token endpoints so it isn't sent on every API request.
REFRESH_TOKEN_COOKIE_PATH = "/api/token"

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # JWT must be first: DRF uses the first authenticator's authenticate_header()
        # to decide between 401 and 403.  SessionAuthentication returns None (no header)
        # which causes DRF to emit 403 for all auth failures — including expired tokens —
        # so the frontend's 401→refresh flow never fires.  JWT first → 401 → refresh. ✓
        # Vlastná trieda: pribalí profil do toho istého dotazu, ktorým sa
        # načítava používateľ — rolový systém sa naň pýta pri každom requeste.
        "api.authentication.ProfileAwareJWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "api.exception_handlers.custom_exception_handler",
    # Global (not per-user) caps on the two endpoints that saturate first
    # under load — see api/throttles.py and load-tests/README.md "Measured
    # Capacity". Env-overridable so raising backend capacity (CPU/replicas)
    # doesn't need a code change to move the ceiling.
    "DEFAULT_THROTTLE_RATES": {
        "login_global": os.environ.get("LOGIN_GLOBAL_THROTTLE_RATE", "150/min"),
        "order_submit_global": os.environ.get(
            "ORDER_SUBMIT_GLOBAL_THROTTLE_RATE", "150/min"
        ),
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name}:{lineno} {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "admin_log_buffer": {
            "class": "api.logging_buffer.InMemoryLogHandler",
            "formatter": "verbose",
            "level": "INFO",
        },
    },
    "root": {
        "handlers": ["console", "admin_log_buffer"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "admin_log_buffer"],
            "level": "INFO",
            "propagate": False,
        },
        "api": {
            "handlers": ["console", "admin_log_buffer"],
            "level": "INFO",
            "propagate": False,
        },
        "celery": {
            "handlers": ["console", "admin_log_buffer"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# drf-spectacular – OpenAPI / Swagger configuration
SPECTACULAR_SETTINGS = {
    "TITLE": "Zdravý projekt API",
    "DESCRIPTION": (
        "REST API for the Zdravý projekt catering order management system.\n\n"
        "## Authentication\n"
        "All protected endpoints require a JWT **Bearer** token obtained from "
        "`POST /api/token/`.  Include it in the `Authorization` header:\n"
        "```\nAuthorization: Bearer <access_token>\n```\n\n"
        "## Error Response Format\n"
        "All API errors follow a standardized format:\n"
        "```json\n"
        "{\n"
        '  "error": {\n'
        '    "code": "error_code",\n'
        '    "message": "Human-readable error message",\n'
        '    "details": {\n'
        '      "field": "additional context"\n'
        "    }\n"
        "  }\n"
        "}\n"
        "```\n\n"
        "The `error.code` field contains a machine-readable error code (e.g., "
        "`invalid_credentials`, `rate_limit_exceeded`) that you can use for "
        "programmatic error handling. The `error.message` field contains a "
        "human-readable message that may be localized. The `error.details` "
        "object provides additional context specific to the error type.\n\n"
        "For a complete reference of error codes, see the project documentation."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    "TAGS": [
        {
            "name": "auth",
            "description": "Authentication – token obtain/refresh, password reset",
        },
        {
            "name": "registration",
            "description": "User registration and email verification",
        },
        {"name": "orders", "description": "Daily and planned order management"},
        {"name": "user", "description": "User profile and client settings"},
        {"name": "diets", "description": "Diet catalogue"},
        {
            "name": "admin",
            "description": "Admin-only endpoints (users, reports, settings)",
        },
    ],
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": False,
    },
    "SECURITY": [{"jwtAuth": []}],
    "SECURITY_SCHEMES": {
        "jwtAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    },
}
