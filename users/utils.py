import os
import uuid
import boto3
import requests


def generate_s3_presigned_url(key: str, content_type: str, expires_in: int = 3600):
    """
    Returns a presigned PUT URL and the final file URL.
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


FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY") or "YOUR_FCM_SERVER_KEY"
FCM_URL = "https://fcm.googleapis.com/fcm/send"


def send_fcm(token: str, title: str, body: str, data: dict | None = None):
    """
    Real FCM send using HTTP.
    """
    if not token or not FCM_SERVER_KEY:
        return

    headers = {
        "Authorization": f"key={FCM_SERVER_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "to": token,
        "notification": {
            "title": title,
            "body": body,
        },
        "data": data or {},
        "priority": "high",
    }

    try:
        requests.post(FCM_URL, json=payload, headers=headers, timeout=5)
    except Exception as e:
        # You might want to log this
        print("FCM error:", e)


def send_fcm_to_manager(manager_profile, title: str, body: str, data: dict | None = None):
    token = getattr(manager_profile, "fcm_token", None)
    if token:
        send_fcm(token, title, body, data)


def send_fcm_to_owner(title: str, body: str, data: dict | None = None):
    from owner.models import OwnerDevice  # local import to avoid circular

    for device in OwnerDevice.objects.filter(is_active=True):
        if device.fcm_token:
            send_fcm(device.fcm_token, title, body, data)
