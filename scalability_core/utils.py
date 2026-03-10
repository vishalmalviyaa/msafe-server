import json
import os
from typing import Any, Dict

import requests
from django.utils import timezone

try:
    import boto3
except ImportError:  # pragma: no cover
    boto3 = None  # type: ignore


class FcmError(Exception):
    pass


def send_fcm_data_message(token: str, data: Dict[str, Any]) -> str:
    """Send a data-only FCM message via legacy HTTP API.

    Expects env var FCM_SERVER_KEY to be set.
    Returns FCM message_id on success.
    """
    server_key = os.environ.get("FCM_SERVER_KEY")
    if not server_key:
        raise FcmError("FCM_SERVER_KEY environment variable is not set")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"key={server_key}",
    }
    payload = {
        "to": token,
        "priority": "high",
        "data": data,
    }
    resp = requests.post(
        "https://fcm.googleapis.com/fcm/send",
        headers=headers,
        data=json.dumps(payload),
        timeout=10,
    )
    if resp.status_code != 200:
        raise FcmError(f"FCM HTTP {resp.status_code}: {resp.text}")

    body = resp.json()
    if body.get("failure"):
        raise FcmError(f"FCM failure: {body}")
    return body.get("results", [{}])[0].get("message_id", "")


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
