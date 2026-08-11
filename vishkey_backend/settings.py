import os
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv
import dj_database_url


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def env_int(name, default):
    value = os.getenv(name)

    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        raise RuntimeError(
            f"{name} must be a valid integer."
        )


# ============================================================
# CORE
# ============================================================

DEBUG = env_bool(
    "DJANGO_DEBUG",
    False,
)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")

if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-secret-change-me"
    else:
        raise RuntimeError(
            "DJANGO_SECRET_KEY is required in production."
        )


# ============================================================
# HOSTS
# ============================================================

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "DJANGO_ALLOWED_HOSTS",
        "api.msafe.shop,msafe-server.onrender.com",
    ).split(",")
    if host.strip()
]


# ============================================================
# CSRF
# ============================================================

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "https://api.msafe.shop",
    ).split(",")
    if origin.strip()
]


# ============================================================
# REVERSE PROXY / HTTPS
# ============================================================

SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https",
)

USE_X_FORWARDED_HOST = env_bool(
    "DJANGO_USE_X_FORWARDED_HOST",
    False,
)


# ============================================================
# APPLICATIONS
# ============================================================

INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # WhiteNoise
    "whitenoise.runserver_nostatic",

    # REST API
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",

    # Celery
    "django_celery_results",
    "django_celery_beat",

    # Project
    "owner",
    "manager",
    "users",
    "scalability_core",
]


# ============================================================
# MIDDLEWARE
# ============================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",

    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",

    "django.middleware.common.CommonMiddleware",

    "django.middleware.csrf.CsrfViewMiddleware",

    "django.contrib.auth.middleware.AuthenticationMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",

    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ============================================================
# URL / WSGI
# ============================================================

ROOT_URLCONF = "vishkey_backend.urls"

WSGI_APPLICATION = "vishkey_backend.wsgi.application"


# ============================================================
# TEMPLATES
# ============================================================

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


# ============================================================
# DATABASE
# ============================================================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not configured."
    )


DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,

        conn_max_age=env_int(
            "DATABASE_CONN_MAX_AGE",
            600,
        ),

        conn_health_checks=True,

        ssl_require=env_bool(
            "DATABASE_SSL_REQUIRE",
            True,
        ),
    )
}


# Database connection options
DATABASES["default"].setdefault(
    "OPTIONS",
    {}
)

DATABASES["default"]["OPTIONS"].setdefault(
    "connect_timeout",
    env_int(
        "DATABASE_CONNECT_TIMEOUT",
        10,
    ),
)


# ============================================================
# PASSWORD VALIDATION
# ============================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },

    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
        "OPTIONS": {
            "min_length": 10,
        },
    },

    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },

    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]


# ============================================================
# INTERNATIONALIZATION
# ============================================================

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Kolkata"

USE_I18N = True

USE_TZ = True


# ============================================================
# STATIC FILES
# ============================================================

STATIC_URL = "/static/"

STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_STORAGE = (
    "whitenoise.storage."
    "CompressedManifestStaticFilesStorage"
)


# ============================================================
# MEDIA
# ============================================================

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"


# ============================================================
# DEFAULT PRIMARY KEY
# ============================================================

DEFAULT_AUTO_FIELD = (
    "django.db.models.BigAutoField"
)


# ============================================================
# DJANGO REST FRAMEWORK
# ============================================================

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],

    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],

    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],

    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],

    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "300/min",
    },

    "DEFAULT_PAGINATION_CLASS": (
        "rest_framework.pagination."
        "PageNumberPagination"
    ),

    "PAGE_SIZE": 50,
}


# ============================================================
# JWT
# ============================================================

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=60
    ),

    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=7
    ),

    "ROTATE_REFRESH_TOKENS": True,

    "BLACKLIST_AFTER_ROTATION": True,

    "UPDATE_LAST_LOGIN": True,

    "ALGORITHM": "HS256",

    "SIGNING_KEY": SECRET_KEY,

    "AUTH_HEADER_TYPES": (
        "Bearer",
    ),
}


# ============================================================
# APPLICATION SECURITY KEYS
# ============================================================

DPC_API_KEY = os.getenv("DPC_API_KEY")

if not DPC_API_KEY:
    if DEBUG:
        DPC_API_KEY = "dev-dpc-key-change-me"
    else:
        raise RuntimeError(
            "DPC_API_KEY is required in production."
        )


FCM_SERVER_KEY = os.getenv(
    "FCM_SERVER_KEY",
    "",
)


# ============================================================
# REDIS
# ============================================================

REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379/0",
)


# ============================================================
# CACHE
# ============================================================

CACHES = {
    "default": {
        "BACKEND": (
            "django.core.cache.backends.redis."
            "RedisCache"
        ),

        "LOCATION": REDIS_URL,

        "TIMEOUT": 300,

        "OPTIONS": {
            "socket_connect_timeout": 5,
            "socket_timeout": 5,
        },
    },
}


# ============================================================
# CELERY
# ============================================================

CELERY_BROKER_URL = REDIS_URL

CELERY_RESULT_BACKEND = REDIS_URL

CELERY_ACCEPT_CONTENT = [
    "json",
]

CELERY_TASK_SERIALIZER = "json"

CELERY_RESULT_SERIALIZER = "json"

CELERY_TIMEZONE = TIME_ZONE

CELERY_ENABLE_UTC = True

CELERY_TASK_TRACK_STARTED = True

CELERY_TASK_TIME_LIMIT = 300

CELERY_TASK_SOFT_TIME_LIMIT = 240

CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True


# ============================================================
# CELERY BEAT
# ============================================================

CELERY_BEAT_SCHEDULER = (
    "django_celery_beat.schedulers."
    "DatabaseScheduler"
)


# ============================================================
# SESSION SECURITY
# ============================================================

SESSION_COOKIE_NAME = "msafe_session"

SESSION_COOKIE_HTTPONLY = True

SESSION_COOKIE_SAMESITE = "Lax"

SESSION_COOKIE_SECURE = not DEBUG

SESSION_COOKIE_AGE = 60 * 60 * 24 * 7


# ============================================================
# CSRF SECURITY
# ============================================================

CSRF_COOKIE_NAME = "msafe_csrf"

CSRF_COOKIE_HTTPONLY = False

CSRF_COOKIE_SECURE = not DEBUG

CSRF_COOKIE_SAMESITE = "Lax"

CSRF_USE_SESSIONS = False


# ============================================================
# SECURITY HEADERS
# ============================================================

SECURE_CONTENT_TYPE_NOSNIFF = True

SECURE_BROWSER_XSS_FILTER = True

X_FRAME_OPTIONS = "DENY"

SECURE_REFERRER_POLICY = (
    "strict-origin-when-cross-origin"
)


# ============================================================
# HTTPS SECURITY
# ============================================================

if not DEBUG:

    SECURE_SSL_REDIRECT = True

    SECURE_HSTS_SECONDS = env_int(
        "DJANGO_HSTS_SECONDS",
        31536000,
    )

    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
        "DJANGO_HSTS_INCLUDE_SUBDOMAINS",
        True,
    )

    SECURE_HSTS_PRELOAD = env_bool(
        "DJANGO_HSTS_PRELOAD",
        True,
    )


# ============================================================
# ADMIN
# ============================================================

ADMIN_URL = "admin/"


# ============================================================
# FILE UPLOAD LIMITS
# ============================================================

DATA_UPLOAD_MAX_MEMORY_SIZE = env_int(
    "DATA_UPLOAD_MAX_MEMORY_SIZE",
    10 * 1024 * 1024,
)

FILE_UPLOAD_MAX_MEMORY_SIZE = env_int(
    "FILE_UPLOAD_MAX_MEMORY_SIZE",
    10 * 1024 * 1024,
)


# ============================================================
# LOGGING
# ============================================================

LOG_LEVEL = os.getenv(
    "DJANGO_LOG_LEVEL",
    "INFO",
).upper()


LOGGING = {
    "version": 1,

    "disable_existing_loggers": False,

    "formatters": {
        "production": {
            "format": (
                "{levelname} "
                "{asctime} "
                "{name} "
                "{message}"
            ),
            "style": "{",
        },
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "production",
        },
    },

    "root": {
        "handlers": [
            "console",
        ],
        "level": LOG_LEVEL,
    },

    "loggers": {
        "django": {
            "handlers": [
                "console",
            ],
            "level": LOG_LEVEL,
            "propagate": False,
        },

        "django.request": {
            "handlers": [
                "console",
            ],
            "level": "ERROR",
            "propagate": False,
        },

        "django.db.backends": {
            "handlers": [
                "console",
            ],
            "level": "WARNING",
            "propagate": False,
        },
    },
}


# ============================================================
# PRODUCTION SAFETY CHECKS
# ============================================================

if not DEBUG:

    if SECRET_KEY in {
        "dev-secret",
        "dev-only-secret-change-me",
    }:
        raise RuntimeError(
            "Unsafe SECRET_KEY detected in production."
        )

    if len(SECRET_KEY) < 50:
        raise RuntimeError(
            "DJANGO_SECRET_KEY should be at least "
            "50 characters in production."
        )

    if "api.msafe.shop" not in ALLOWED_HOSTS:
        raise RuntimeError(
            "api.msafe.shop must be present "
            "in ALLOWED_HOSTS."
        )

    if "https://api.msafe.shop" not in CSRF_TRUSTED_ORIGINS:
        raise RuntimeError(
            "https://api.msafe.shop must be present "
            "in CSRF_TRUSTED_ORIGINS."
        )

    if DPC_API_KEY in {
        "super-secret",
        "dev-dpc-key",
        "dev-dpc-key-change-me",
    }:
        raise RuntimeError(
            "Unsafe DPC_API_KEY detected in production."
        )