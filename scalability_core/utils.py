import os
from typing import Any, Dict

import requests
from django.conf import settings
from django.utils import timezone

try:
    import boto3
except ImportError:  # pragma: no cover
    boto3 = None  # type: ignore

# Reuse the single OAuth2/FCM-v1 implementation instead of duplicating it -
# the old legacy "server key" HTTP API this file used to call was shut down
# by Google in June 2024 and no longer works.
from users.utils import get_fcm_access_token


class FcmError(Exception):
    pass


def send_fcm_data_message(token: str, data: Dict[str, Any]) -> str:
    """
    Send a data-only FCM message via the FCM HTTP v1 API.
    Returns the FCM message "name" (its message id) on success.
    Raises FcmError on any failure so callers can retry.
    """
    if not token:
        raise FcmError("No FCM token provided")

    project_id = settings.FCM_PROJECT_ID
    if not project_id:
        raise FcmError("FCM_PROJECT_ID is not configured")

    access_token = get_fcm_access_token()
    if not access_token:
        raise FcmError("Could not obtain FCM v1 access token (is the service account configured?)")

    url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; UTF-8",
    }

    str_data = {str(k): str(v) for k, v in (data or {}).items()}

    payload = {
        "message": {
            "token": token,
            "data": str_data,
            "android": {"priority": "high"},
        }
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    if resp.status_code != 200:
        raise FcmError(f"FCM HTTP {resp.status_code}: {resp.text}")

    body = resp.json()
    return body.get("name", "")


def get_s3_presigned_post(
    bucket: str,
    key: str,
    content_type: str,
    expires_in: int = 600,
) -> Dict[str, Any]:
    """Generate an S3 presigned POST.

    Requires boto3 and AWS credentials in environment.
    """
    if boto3 is None:  # pragma: no cover
        raise RuntimeError("boto3 is not installed. pip install boto3")

    session = boto3.session.Session()
    client = session.client("s3")
    return client.generate_presigned_post(
        Bucket=bucket,
        Key=key,
        Fields={"Content-Type": content_type},
        Conditions=[
            {"Content-Type": content_type},
            ["content-length-range", 0, 20 * 1024 * 1024],  # 20 MB
        ],
        ExpiresIn=expires_in,
    )


def utcnow():
    return timezone.now()
