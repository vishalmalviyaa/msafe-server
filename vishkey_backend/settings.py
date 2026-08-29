import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured
import dj_database_url

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def get_secret(name: str, default: str | None = None, required_in_prod: bool = True) -> str:
    """
    Read a secret from the environment.

    In production (DEBUG=False) required secrets MUST be set - we fail loudly
    at startup instead of silently falling back to a hardcoded value that's
    sitting in source control.
    """
    value = os.getenv(name, default)
    debug = os.getenv("DJANGO_DEBUG", "False") == "True"

    if not value and required_in_prod and not debug:
        raise ImproperlyConfigured(
            f"Environment variable {name} is required in production and was not set."
        )

    return value or (default or "")


# ------------------------------------------------
# Core
# ------------------------------------------------

DEBUG = os.getenv("DJANGO_DEBUG", "False") == "True"

SECRET_KEY = get_secret("DJANGO_SECRET_KEY", default="dev-secret-not-for-production")

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "api.msafe.shop",
    "msafe-server.onrender.com",
]
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

CSRF_TRUSTED_ORIGINS = [
    "https://api.msafe.shop",
]


# ------------------------------------------------
# Installed apps
# ------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "whitenoise.runserver_nostatic",

    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",

    "django_celery_results",
    "django_celery_beat",

    "owner",
    "manager",
    "users",
    "scalability_core",
]


# ------------------------------------------------
# Middleware
# ------------------------------------------------

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


ROOT_URLCONF = "vishkey_backend.urls"

WSGI_APPLICATION = "vishkey_backend.wsgi.application"


# ------------------------------------------------
# Templates
# ------------------------------------------------

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


# ------------------------------------------------
# DATABASE (Render compatible)
# ------------------------------------------------

DATABASES = {
    "default": dj_database_url.config(
        default=os.getenv("DATABASE_URL"),
        conn_max_age=600,
        ssl_require=False,
    )
}


# ------------------------------------------------
# Password validation
# ------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ------------------------------------------------
# Internationalization
# ------------------------------------------------

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Kolkata"

USE_I18N = True
USE_TZ = True


# ------------------------------------------------
# Static files
# ------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ------------------------------------------------
# REST FRAMEWORK
# ------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}


# ------------------------------------------------
# JWT
# ------------------------------------------------

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}


# ------------------------------------------------
# SECURITY KEYS
# ------------------------------------------------

# Shared secret the legacy DPC agent puts in the X-DPC-API-KEY header.
DPC_API_KEY = get_secret("DPC_API_KEY", default="dev-only-dpc-key")

# Shared secret a brand-new device uses ONCE to self-register in
# scalability_core (before it has its own per-device token). This is
# intentionally separate from DPC_API_KEY so the two systems can be
# rotated independently.
DEVICE_BOOTSTRAP_KEY = get_secret(
    "DEVICE_BOOTSTRAP_KEY", default="dev-only-bootstrap-key"
)

# --- FCM (HTTP v1 API) ---
# Google shut down the legacy "server key" HTTP API (fcm.googleapis.com/fcm/send)
# in June 2024. Sending now requires OAuth2 via a Firebase service account.
#
# Set FCM_PROJECT_ID to your Firebase project id, and either:
#   - FCM_SERVICE_ACCOUNT_JSON: the full service-account JSON as a string, or
#   - FCM_SERVICE_ACCOUNT_FILE: a path to the service-account JSON file.
FCM_PROJECT_ID = os.getenv("FCM_PROJECT_ID", "")
FCM_SERVICE_ACCOUNT_JSON = os.getenv("FCM_SERVICE_ACCOUNT_JSON", "")
FCM_SERVICE_ACCOUNT_FILE = os.getenv("FCM_SERVICE_ACCOUNT_FILE", "")

# Legacy key kept only so existing deployments don't crash on import;
# no longer used to actually send anything (see users/utils.py).
FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY", "")


# ------------------------------------------------
# Redis
# ------------------------------------------------

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


# ------------------------------------------------
# Cache
# ------------------------------------------------

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}


# ------------------------------------------------
# Celery
# ------------------------------------------------

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"


# ------------------------------------------------
# Logging
# ------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}