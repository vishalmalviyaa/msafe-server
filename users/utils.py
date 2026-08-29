import os
import time
import logging

import boto3
import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


# =========================================================
# S3 PRESIGNED UPLOAD
# =========================================================

def generate_s3_presigned_url(key: str, content_type: str, expires_in: int = 3600):
    """
    Returns (presigned_put_url, final_public_url) for a client to PUT a file
    directly to S3.
    """
    bucket = os.getenv("AWS_STORAGE_BUCKET_NAME")
    region = os.getenv("AWS_S3_REGION_NAME", "ap-south-1")

    if not bucket:
        raise RuntimeError("AWS_STORAGE_BUCKET_NAME not configured")

    s3_client = boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=region,
    )

    presigned_url = s3_client.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires_in,
    )

    final_url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
    return presigned_url, final_url


# =========================================================
# FCM (HTTP v1 API)
# =========================================================
#
# Google shut down the legacy "server key" HTTP API
# (https://fcm.googleapis.com/fcm/send) in June 2024. Sending push
# notifications now requires an OAuth2 access token minted from a Firebase
# service account, posted to:
#
#   https://fcm.googleapis.com/v1/projects/<project-id>/messages:send
#
# We cache the OAuth token in Django's cache (Redis) since it's valid for
# ~1 hour and re-minting it on every push would be wasteful.

_FCM_TOKEN_CACHE_KEY = "fcm:v1:access_token"
_FCM_SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]


def get_fcm_access_token() -> str | None:
    cached = cache.get(_FCM_TOKEN_CACHE_KEY)
    if cached:
        return cached

    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request as GoogleAuthRequest
    except ImportError:
        logger.error(
            "google-auth is not installed; cannot mint FCM v1 access token. "
            "Run: pip install google-auth"
        )
        return None

    creds = None
    try:
        if settings.FCM_SERVICE_ACCOUNT_JSON:
            import json
            info = json.loads(settings.FCM_SERVICE_ACCOUNT_JSON)
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=_FCM_SCOPES
            )
        elif settings.FCM_SERVICE_ACCOUNT_FILE:
            creds = service_account.Credentials.from_service_account_file(
                settings.FCM_SERVICE_ACCOUNT_FILE, scopes=_FCM_SCOPES
            )
        else:
            logger.warning(
                "FCM is not configured (set FCM_SERVICE_ACCOUNT_JSON or "
                "FCM_SERVICE_ACCOUNT_FILE + FCM_PROJECT_ID). Push notifications "
                "will be skipped."
            )
            return None

        creds.refresh(GoogleAuthRequest())
    except Exception:
        logger.exception("Failed to mint FCM v1 access token")
        return None

    # Cache for slightly less than its real lifetime.
    ttl = 3000
    if getattr(creds, "expiry", None):
        ttl = max(60, int(creds.expiry.timestamp() - time.time()) - 60)

    cache.set(_FCM_TOKEN_CACHE_KEY, creds.token, timeout=ttl)
    return creds.token


def send_fcm(token: str, title: str, body: str, data: dict | None = None):
    """
    Send a single push notification via the FCM HTTP v1 API.
    Never raises - logs and returns on failure so a bad push never breaks
    the caller's request/task.
    """
    if not token:
        return

    project_id = settings.FCM_PROJECT_ID
    if not project_id:
        logger.warning("FCM_PROJECT_ID not set; skipping push send.")
        return

    access_token = get_fcm_access_token()
    if not access_token:
        return

    url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; UTF-8",
    }

    # FCM v1 requires all `data` values to be strings.
    str_data = {str(k): str(v) for k, v in (data or {}).items()}

    payload = {
        "message": {
            "token": token,
            "notification": {"title": title, "body": body},
            "data": str_data,
            "android": {"priority": "high"},
        }
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=5)
        if resp.status_code >= 400:
            logger.warning("FCM send failed (%s): %s", resp.status_code, resp.text)
    except requests.RequestException:
        logger.exception("FCM send raised an exception")


def send_fcm_to_manager(manager_profile, title: str, body: str, data: dict | None = None):
    token = getattr(manager_profile, "fcm_token", None)
    if token:
        send_fcm(token, title, body, data)


def send_fcm_to_owner(title: str, body: str, data: dict | None = None):
    from owner.models import OwnerDevice  # local import to avoid circular import

    for device in OwnerDevice.objects.filter(is_active=True):
        if device.fcm_token:
            send_fcm(device.fcm_token, title, body, data)
