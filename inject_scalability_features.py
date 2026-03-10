#!/usr/bin/env python
"""
inject_scalability_stack.py

Run this from your Django project root (same folder as manage.py):

    python inject_scalability_stack.py

This script will:

  - Create a 'scalability_core' app with:
      * DeviceRegistration, FcmCommand, CommandAck, AuditLog, LocationPing models
      * FCM command send + ACK pipeline (Celery tasks)
      * Device ACK endpoint: /api/system/devices/ack/
      * S3 presigned upload endpoint: /api/system/uploads/presign/
      * Health endpoint: /api/system/health/
  - Patch settings.py to add:
      * INSTALLED_APPS entries (rest_framework, scalability_core, celery support)
      * Redis cache + Celery config
      * DRF throttling + basic RBAC hook
      * Logging skeleton
  - Patch root urls.py to include scalability_core URLs under /api/system/

After this, run:

    python manage.py makemigrations scalability_core
    python manage.py migrate

Requirements you must install (if not already):

    pip install celery redis djangorestframework boto3 requests
"""

import os
import re
import sys
from pathlib import Path
from textwrap import dedent

PROJECT_ROOT = Path(__file__).resolve().parent


def find_manage_py() -> Path:
    manage = PROJECT_ROOT / "manage.py"
    if not manage.exists():
        print("ERROR: manage.py not found in current directory.")
        sys.exit(1)
    return manage


def detect_settings_module(manage_path: Path) -> str:
    """
    Try to detect DJANGO_SETTINGS_MODULE from manage.py.
    Fallback: <project_folder>.settings where project_folder has settings.py.
    """
    text = manage_path.read_text(encoding="utf-8")

    # Look for os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xxxx')
    m = re.search(
        r"DJANGO_SETTINGS_MODULE',\s*'([^']+)'", text
    )
    if m:
        return m.group(1)

    # Fallback: search for folder with settings.py
    for child in PROJECT_ROOT.iterdir():
        if child.is_dir() and (child / "settings.py").exists():
            return f"{child.name}.settings"

    print("ERROR: Could not detect DJANGO_SETTINGS_MODULE from manage.py.")
    sys.exit(1)


def get_project_package_name(settings_module: str) -> str:
    # e.g. "myproject.settings" -> "myproject"
    return settings_module.split(".")[0]


def ensure_scalability_app():
    app_dir = PROJECT_ROOT / "scalability_core"
    migrations_dir = app_dir / "migrations"

    app_dir.mkdir(exist_ok=True)
    migrations_dir.mkdir(exist_ok=True)

    # __init__.py
    (app_dir / "__init__.py").write_text("", encoding="utf-8")

    # apps.py
    if not (app_dir / "apps.py").exists():
        (app_dir / "apps.py").write_text(
            dedent(
                """
                from django.apps import AppConfig


                class ScalabilityCoreConfig(AppConfig):
                    default_auto_field = "django.db.models.BigAutoField"
                    name = "scalability_core"
                """
            ).lstrip(),
            encoding="utf-8",
        )

    # models.py
    (app_dir / "models.py").write_text(
        dedent(
            """
            from django.conf import settings
            from django.db import models


            class DeviceRegistration(models.Model):
                \"\"\"Maps a Django user to one or more physical devices + FCM tokens.\"\"\"

                user = models.ForeignKey(
                    settings.AUTH_USER_MODEL,
                    on_delete=models.CASCADE,
                    related_name="device_registrations",
                )
                # Optional: manager / owner relationships can be wired via your domain models
                manager_id = models.IntegerField(null=True, blank=True)
                imei_1 = models.CharField(max_length=32, db_index=True)
                imei_2 = models.CharField(max_length=32, null=True, blank=True)
                device_id = models.CharField(max_length=128, db_index=True)
                fcm_token = models.CharField(max_length=512, db_index=True)
                last_seen = models.DateTimeField(null=True, blank=True)
                last_ip = models.GenericIPAddressField(null=True, blank=True)
                is_active = models.BooleanField(default=True)
                created_at = models.DateTimeField(auto_now_add=True)
                updated_at = models.DateTimeField(auto_now=True)

                class Meta:
                    indexes = [
                        models.Index(fields=["manager_id"]),
                        models.Index(fields=["imei_1"]),
                        models.Index(fields=["device_id"]),
                        models.Index(fields=["fcm_token"]),
                    ]

                def __str__(self) -> str:
                    return f"DeviceRegistration(user={self.user_id}, imei={self.imei_1})"


            class FcmCommand(models.Model):
                \"\"\"Outbound command sent to a device via FCM (LOCK, UNENROLL, etc.).\"\"\"

                ACTION_CHOICES = [
                    ("LOCK", "LOCK"),
                    ("UNLOCK", "UNLOCK"),
                    ("UNENROLL", "UNENROLL"),
                    ("MESSAGE", "MESSAGE"),
                    ("OTHER", "OTHER"),
                ]

                STATUS_CHOICES = [
                    ("PENDING", "PENDING"),  # created, not yet attempted
                    ("SENT", "SENT"),        # sent to FCM
                    ("ACKED", "ACKED"),      # device acknowledged
                    ("FAILED", "FAILED"),    # permanent failure
                ]

                device = models.ForeignKey(
                    DeviceRegistration,
                    on_delete=models.CASCADE,
                    related_name="commands",
                )
                action = models.CharField(max_length=32, choices=ACTION_CHOICES)
                payload = models.JSONField(default=dict, blank=True)
                status = models.CharField(
                    max_length=16, choices=STATUS_CHOICES, default="PENDING"
                )
                fcm_message_id = models.CharField(
                    max_length=128, null=True, blank=True, db_index=True
                )
                retry_count = models.PositiveIntegerField(default=0)
                next_retry_at = models.DateTimeField(null=True, blank=True)
                created_at = models.DateTimeField(auto_now_add=True)
                updated_at = models.DateTimeField(auto_now=True)

                class Meta:
                    indexes = [
                        models.Index(fields=["status"]),
                        models.Index(fields=["action"]),
                    ]

                def __str__(self) -> str:
                    return f"FcmCommand(device={self.device_id}, action={self.action}, status={self.status})"


            class CommandAck(models.Model):
                \"\"\"Raw ACK from a device for a given FcmCommand.\"\"\"

                command = models.ForeignKey(
                    FcmCommand,
                    on_delete=models.CASCADE,
                    related_name="acks",
                )
                status = models.CharField(max_length=32)  # SUCCESS / FAILED / OTHER
                raw_payload = models.JSONField(default=dict, blank=True)
                created_at = models.DateTimeField(auto_now_add=True)

                def __str__(self) -> str:
                    return f"CommandAck(command={self.command_id}, status={self.status})"


            class AuditLog(models.Model):
                \"\"\"Immutable audit trail for sensitive actions.

                Examples:
                  - DELETE_USER
                  - ENROLL_DEVICE
                  - UNENROLL_DEVICE
                  - LOCK_DEVICE
                  - UNLOCK_DEVICE
                \"\"\"

                ACTOR_TYPE_CHOICES = [
                    ("owner", "Owner"),
                    ("manager", "Manager"),
                    ("system", "System"),
                ]

                STATUS_CHOICES = [
                    ("PENDING", "PENDING"),
                    ("SUCCESS", "SUCCESS"),
                    ("FAILED", "FAILED"),
                ]

                actor_type = models.CharField(max_length=16, choices=ACTOR_TYPE_CHOICES)
                actor_id = models.IntegerField(null=True, blank=True)
                target_user = models.ForeignKey(
                    settings.AUTH_USER_MODEL,
                    on_delete=models.SET_NULL,
                    null=True,
                    blank=True,
                    related_name="audit_logs",
                )
                device = models.ForeignKey(
                    DeviceRegistration,
                    on_delete=models.SET_NULL,
                    null=True,
                    blank=True,
                    related_name="audit_logs",
                )
                action = models.CharField(max_length=64)
                status = models.CharField(
                    max_length=16, choices=STATUS_CHOICES, default="PENDING"
                )
                details = models.JSONField(default=dict, blank=True)
                created_at = models.DateTimeField(auto_now_add=True)
                resolved_at = models.DateTimeField(null=True, blank=True)

                class Meta:
                    indexes = [
                        models.Index(fields=["actor_type", "actor_id"]),
                        models.Index(fields=["action"]),
                        models.Index(fields=["status"]),
                        models.Index(fields=["created_at"]),
                    ]

                def __str__(self) -> str:
                    return f"AuditLog(action={self.action}, status={self.status})"


            class LocationPing(models.Model):
                \"\"\"Stores live location & SIM metadata snapshots from devices (time-series).\"\"\"

                device = models.ForeignKey(
                    DeviceRegistration,
                    on_delete=models.CASCADE,
                    related_name="location_pings",
                )
                latitude = models.DecimalField(max_digits=9, decimal_places=6)
                longitude = models.DecimalField(max_digits=9, decimal_places=6)
                accuracy_m = models.FloatField(null=True, blank=True)
                sim_numbers = models.JSONField(default=list, blank=True)
                captured_at = models.DateTimeField()  # device local timestamp
                received_at = models.DateTimeField(auto_now_add=True)

                class Meta:
                    indexes = [
                        models.Index(fields=["device", "captured_at"]),
                        models.Index(fields=["received_at"]),
                    ]

                def __str__(self) -> str:
                    return f"LocationPing(device={self.device_id}, lat={self.latitude}, lon={self.longitude})"
            """
        ).lstrip(),
        encoding="utf-8",
    )

    # utils.py (FCM + S3 helpers)
    (app_dir / "utils.py").write_text(
        dedent(
            """
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
                \"\"\"Send a data-only FCM message via legacy HTTP API.

                Expects env var FCM_SERVER_KEY to be set.
                Returns FCM message_id on success.
                \"\"\"
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
                \"\"\"Generate an S3 presigned POST.

                Requires boto3 and AWS credentials in environment.
                \"\"\"
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
            """
        ).lstrip(),
        encoding="utf-8",
    )

    # tasks.py (Celery tasks)
    (app_dir / "tasks.py").write_text(
        dedent(
            """
            import logging
            from datetime import timedelta

            from celery import shared_task
            from django.db import transaction
            from django.utils import timezone

            from .models import FcmCommand, CommandAck, AuditLog
            from .utils import FcmError, send_fcm_data_message, utcnow

            logger = logging.getLogger(__name__)


            @shared_task(bind=True, max_retries=5, default_retry_delay=30)
            def send_fcm_command_task(self, command_id: int) -> None:
                \"\"\"Send a single FcmCommand via FCM with retry.

                States:
                  - PENDING -> SENT (on success, waiting for ACK)
                  - PENDING -> FAILED (on permanent error after retries)
                \"\"\"
                try:
                    command = FcmCommand.objects.select_related("device").get(pk=command_id)
                except FcmCommand.DoesNotExist:
                    logger.warning("FcmCommand %s does not exist", command_id)
                    return

                if command.status not in ("PENDING", "FAILED"):
                    logger.info(
                        "FcmCommand %s already processed with status %s",
                        command_id,
                        command.status,
                    )
                    return

                device = command.device
                data = {
                    "action": command.action,
                    "command_id": command.id,
                    "user_id": device.user_id,
                    "device_id": device.device_id,
                    "imei_1": device.imei_1,
                    "payload": command.payload,
                }

                try:
                    message_id = send_fcm_data_message(device.fcm_token, data)
                except FcmError as exc:
                    logger.exception("Error sending FCM for command %s: %s", command_id, exc)
                    # Update for retry
                    with transaction.atomic():
                        command.retry_count += 1
                        command.next_retry_at = utcnow() + timedelta(
                            seconds=min(300, 30 * (2 ** command.retry_count))
                        )
                        if command.retry_count >= 5:
                            command.status = "FAILED"
                        command.save(update_fields=["retry_count", "next_retry_at", "status"])
                    if command.status != "FAILED":
                        raise self.retry(exc=exc)
                    return

                with transaction.atomic():
                    command.status = "SENT"
                    command.fcm_message_id = message_id
                    command.next_retry_at = utcnow() + timedelta(minutes=10)
                    command.save(update_fields=["status", "fcm_message_id", "next_retry_at"])

                    AuditLog.objects.create(
                        actor_type="manager",
                        actor_id=command.device.manager_id,
                        target_user=command.device.user,
                        device=command.device,
                        action=f"FCM_{command.action}",
                        status="PENDING",
                        details={"command_id": command.id, "fcm_message_id": message_id},
                    )


            @shared_task
            def retry_stale_fcm_commands_task() -> None:
                \"\"\"Periodic task: re-send stale SENT/PENDING commands that lack ACK.\"\"\"
                now = timezone.now()
                qs = FcmCommand.objects.filter(
                    status__in=["PENDING", "SENT"],
                    next_retry_at__isnull=False,
                    next_retry_at__lte=now,
                )
                for cmd in qs[:500]:
                    send_fcm_command_task.delay(cmd.id)


            @shared_task
            def reconcile_command_ack_task(command_id: int) -> None:
                \"\"\"Reconcile CommandAck with FcmCommand -> finalize AuditLog.\"\"\"
                try:
                    command = (
                        FcmCommand.objects.select_related("device")
                        .prefetch_related("acks")
                        .get(pk=command_id)
                    )
                except FcmCommand.DoesNotExist:
                    return

                acks = list(command.acks.all())
                if not acks:
                    return

                latest = acks[-1]
                status = "SUCCESS" if latest.status.upper() == "SUCCESS" else "FAILED"

                command.status = "ACKED" if status == "SUCCESS" else "FAILED"
                command.save(update_fields=["status"])

                AuditLog.objects.filter(
                    details__command_id=command.id,
                    action__startswith="FCM_",
                    status="PENDING",
                ).update(
                    status=status,
                    resolved_at=utcnow(),
                )
            """
        ).lstrip(),
        encoding="utf-8",
    )

    # permissions.py (RBAC hook via Django groups)
    (app_dir / "permissions.py").write_text(
        dedent(
            """
            from rest_framework.permissions import BasePermission, SAFE_METHODS


            class IsOwnerOrManager(BasePermission):
                \"\"\"Simple RBAC via Django groups.

                - Users in group "owner" are treated as Owners.
                - Users in group "manager" are treated as Managers.
                Adjust to match your real roles if needed.
                \"\"\"

                def has_permission(self, request, view):
                    user = request.user
                    if not user or not user.is_authenticated:
                        return False
                    if user.is_superuser:
                        return True
                    if request.method in SAFE_METHODS:
                        return True
                    groups = set(user.groups.values_list("name", flat=True))
                    if "owner" in groups or "manager" in groups:
                        return True
                    return False
            """
        ).lstrip(),
        encoding="utf-8",
    )

    # serializers.py
    (app_dir / "serializers.py").write_text(
        dedent(
            """
            from rest_framework import serializers

            from .models import DeviceRegistration, FcmCommand, CommandAck, AuditLog, LocationPing


            class DeviceRegistrationSerializer(serializers.ModelSerializer):
                class Meta:
                    model = DeviceRegistration
                    fields = [
                        "id",
                        "user",
                        "manager_id",
                        "imei_1",
                        "imei_2",
                        "device_id",
                        "fcm_token",
                        "last_seen",
                        "last_ip",
                        "is_active",
                        "created_at",
                        "updated_at",
                    ]
                    read_only_fields = ["id", "created_at", "updated_at"]


            class CommandAckSerializer(serializers.Serializer):
                action = serializers.CharField()
                command_id = serializers.IntegerField(required=False)
                fcm_message_id = serializers.CharField(required=False, allow_blank=True)
                status = serializers.CharField()
                payload = serializers.JSONField(required=False)


            class PresignUploadRequestSerializer(serializers.Serializer):
                filename = serializers.CharField()
                content_type = serializers.CharField()


            class PresignUploadResponseSerializer(serializers.Serializer):
                url = serializers.CharField()
                fields = serializers.JSONField()


            class AuditLogSerializer(serializers.ModelSerializer):
                class Meta:
                    model = AuditLog
                    fields = "__all__"


            class LocationPingSerializer(serializers.ModelSerializer):
                class Meta:
                    model = LocationPing
                    fields = "__all__"
            """
        ).lstrip(),
        encoding="utf-8",
    )

    # views.py
    (app_dir / "views.py").write_text(
        dedent(
            """
            import os
            import uuid

            from django.db import transaction
            from django.http import JsonResponse
            from django.utils import timezone
            from rest_framework import status
            from rest_framework.decorators import api_view, permission_classes
            from rest_framework.permissions import IsAuthenticated, AllowAny
            from rest_framework.response import Response
            from rest_framework.views import APIView

            from .models import DeviceRegistration, FcmCommand, CommandAck, AuditLog
            from .permissions import IsOwnerOrManager
            from .serializers import (
                CommandAckSerializer,
                PresignUploadRequestSerializer,
                PresignUploadResponseSerializer,
            )
            from .tasks import reconcile_command_ack_task
            from .utils import get_s3_presigned_post


            @api_view(["GET"])
            @permission_classes([AllowAny])
            def health(request):
                return Response({"status": "ok", "time": timezone.now().isoformat()})


            class DeviceAckView(APIView):
                \"\"\"Endpoint called by DPC app to ACK commands.

                POST /api/system/devices/ack/
                body:
                {
                    "action": "UNENROLL_ACK",
                    "command_id": 123,
                    "status": "SUCCESS",
                    "payload": {...}
                }
                \"\"\"

                permission_classes = [AllowAny]

                def post(self, request, *args, **kwargs):
                    serializer = CommandAckSerializer(data=request.data)
                    serializer.is_valid(raise_exception=True)
                    data = serializer.validated_data

                    command_id = data.get("command_id")
                    fcm_message_id = data.get("fcm_message_id")
                    status_str = data["status"]

                    try:
                        if command_id:
                            command = FcmCommand.objects.select_related("device").get(
                                pk=command_id
                            )
                        else:
                            command = FcmCommand.objects.select_related("device").get(
                                fcm_message_id=fcm_message_id
                            )
                    except FcmCommand.DoesNotExist:
                        return Response(
                            {"detail": "Command not found"},
                            status=status.HTTP_404_NOT_FOUND,
                        )

                    with transaction.atomic():
                        CommandAck.objects.create(
                            command=command,
                            status=status_str,
                            raw_payload=data.get("payload") or {},
                        )
                        # Update device last_seen
                        device = command.device
                        device.last_seen = timezone.now()
                        device.save(update_fields=["last_seen"])

                    # Trigger async reconciliation
                    reconcile_command_ack_task.delay(command.id)

                    return Response({"ok": True})


            class PresignUploadView(APIView):
                \"\"\"Return S3 presigned POST for uploads to S3.

                GET or POST /api/system/uploads/presign/?filename=...&content_type=...

                Requires env:
                  - FILE_UPLOAD_BUCKET (S3 bucket name)
                \"\"\"

                permission_classes = [IsAuthenticated, IsOwnerOrManager]

                def get(self, request, *args, **kwargs):
                    serializer = PresignUploadRequestSerializer(data=request.query_params)
                    serializer.is_valid(raise_exception=True)
                    return self._create_presign(serializer.validated_data)

                def post(self, request, *args, **kwargs):
                    serializer = PresignUploadRequestSerializer(data=request.data)
                    serializer.is_valid(raise_exception=True)
                    return self._create_presign(serializer.validated_data)

                def _create_presign(self, data):
                    bucket = os.environ.get("FILE_UPLOAD_BUCKET")
                    if not bucket:
                        return Response(
                            {"detail": "FILE_UPLOAD_BUCKET is not configured"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        )

                    filename = data["filename"]
                    content_type = data["content_type"]

                    ext = ""
                    if "." in filename:
                        ext = "." + filename.split(".")[-1]
                    key = f"uploads/{timezone.now().strftime('%Y/%m/%d')}/{uuid.uuid4()}{ext}"

                    presigned = get_s3_presigned_post(
                        bucket=bucket,
                        key=key,
                        content_type=content_type,
                    )
                    out = {
                        "url": presigned["url"],
                        "fields": presigned["fields"],
                        "key": key,
                        "bucket": bucket,
                    }
                    resp = PresignUploadResponseSerializer(out)
                    return Response(resp.data)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    # urls.py
    (app_dir / "urls.py").write_text(
        dedent(
            """
            from django.urls import path

            from .views import DeviceAckView, PresignUploadView, health

            app_name = "scalability_core"

            urlpatterns = [
                path("health/", health, name="health"),
                path("devices/ack/", DeviceAckView.as_view(), name="device-ack"),
                path("uploads/presign/", PresignUploadView.as_view(), name="presign-upload"),
            ]
            """
        ).lstrip(),
        encoding="utf-8",
    )


def patch_settings(settings_module: str):
    project_package = get_project_package_name(settings_module)
    settings_path = PROJECT_ROOT / project_package / "settings.py"
    if not settings_path.exists():
        print(f"ERROR: settings.py not found at {settings_path}")
        sys.exit(1)

    text = settings_path.read_text(encoding="utf-8")

    marker = "# === SCALABILITY_STACK_START ==="
    if marker in text:
        print("settings.py already patched (marker found). Skipping settings patch.")
        return

    # Ensure rest_framework and scalability_core in INSTALLED_APPS
    def inject_into_installed_apps(src: str) -> str:
        pattern = r"INSTALLED_APPS\s*=\s*\[([^\]]*)\]"
        m = re.search(pattern, src, re.DOTALL)
        if not m:
            return src
        body = m.group(1)
        additions = []
        if "'rest_framework'" not in body and '"rest_framework"' not in body:
            additions.append("    'rest_framework',")
        if "'scalability_core'" not in body and '"scalability_core"' not in body:
            additions.append("    'scalability_core',")
        if "'django_celery_results'" not in body and '"django_celery_results"' not in body:
            additions.append("    'django_celery_results',")
        if "'django_celery_beat'" not in body and '"django_celery_beat"' not in body:
            additions.append("    'django_celery_beat',")
        new_body = body + "\n" + "\n".join(additions)
        return re.sub(pattern, f"INSTALLED_APPS = [\n{new_body}\n]", src, flags=re.DOTALL)

    text = inject_into_installed_apps(text)

    patch_block = dedent(
        f"""
        {marker}
        # Auto-injected scalability / FCM / Celery / DRF configuration.
        # Redis cache + Celery broker
        import os

        REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

        CACHES = {{
            "default": {{
                "BACKEND": "django_redis.cache.RedisCache",
                "LOCATION": REDIS_URL,
                "OPTIONS": {{
                    "CLIENT_CLASS": "django_redis.client.DefaultClient",
                }},
            }}
        }}

        CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
        CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)
        CELERY_ACCEPT_CONTENT = ["json"]
        CELERY_TASK_SERIALIZER = "json"
        CELERY_RESULT_SERIALIZER = "json"
        CELERY_TIMEZONE = "Asia/Kolkata"

        # DRF defaults with simple throttling
        REST_FRAMEWORK = {{
            "DEFAULT_AUTHENTICATION_CLASSES": [
                "rest_framework.authentication.SessionAuthentication",
                "rest_framework.authentication.BasicAuthentication",
            ],
            "DEFAULT_PERMISSION_CLASSES": [
                "rest_framework.permissions.IsAuthenticated",
            ],
            "DEFAULT_THROTTLE_CLASSES": [
                "rest_framework.throttling.UserRateThrottle",
                "rest_framework.throttling.AnonRateThrottle",
            ],
            "DEFAULT_THROTTLE_RATES": {{
                "user": "1000/hour",
                "anon": "100/hour",
            }},
        }}

        # Basic logging skeleton
        LOGGING = {{
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": {{
                "console": {{
                    "class": "logging.StreamHandler",
                }},
            }},
            "root": {{
                "handlers": ["console"],
                "level": "INFO",
            }},
            "loggers": {{
                "scalability_core": {{
                    "handlers": ["console"],
                    "level": "INFO",
                    "propagate": False,
                }},
                "celery": {{
                    "handlers": ["console"],
                    "level": "INFO",
                    "propagate": False,
                }},
            }},
        }}
        # === SCALABILITY_STACK_END ===
        """
    )

    text += "\n\n" + patch_block
    settings_path.write_text(text, encoding="utf-8")
    print("Patched settings.py with scalability stack config.")


def ensure_celery_py(settings_module: str):
    project_package = get_project_package_name(settings_module)
    celery_path = PROJECT_ROOT / project_package / "celery.py"
    init_path = PROJECT_ROOT / project_package / "__init__.py"

    if not celery_path.exists():
        celery_path.write_text(
            dedent(
                f"""
                import os

                from celery import Celery

                os.environ.setdefault("DJANGO_SETTINGS_MODULE", "{settings_module}")

                app = Celery("{project_package}")
                app.config_from_object("django.conf:settings", namespace="CELERY")
                app.autodiscover_tasks()
                """
            ).lstrip(),
            encoding="utf-8",
        )
        print("Created celery.py.")

    init_text = init_path.read_text(encoding="utf-8")
    if "from .celery import app as celery_app" not in init_text:
        init_text += "\n\nfrom .celery import app as celery_app\n\n__all__ = ('celery_app',)\n"
        init_path.write_text(init_text, encoding="utf-8")
        print("Wired celery_app into __init__.py.")


def patch_urls(settings_module: str):
    project_package = get_project_package_name(settings_module)
    urls_path = PROJECT_ROOT / project_package / "urls.py"
    if not urls_path.exists():
        print(f"ERROR: urls.py not found at {urls_path}")
        sys.exit(1)

    text = urls_path.read_text(encoding="utf-8")

    if "scalability_core.urls" in text:
        print("Root urls.py already includes scalability_core. Skipping urls patch.")
        return

    # Ensure include imported
    if "from django.urls import path, include" not in text:
        if "from django.urls import path" in text:
            text = text.replace(
                "from django.urls import path",
                "from django.urls import path, include",
            )
        elif "from django.urls import include, path" not in text:
            # Prepend import if missing
            text = "from django.urls import path, include\n" + text

    # Inject into urlpatterns
    pattern = r"urlpatterns\s*=\s*\[(.*?)\]"
    m = re.search(pattern, text, re.DOTALL)
    if not m:
        print("WARNING: Could not find urlpatterns list to patch.")
        return

    body = m.group(1)
    addition = "    path('api/system/', include('scalability_core.urls')),"

    if addition not in body:
        new_body = body + "\n" + addition + "\n"
        text = re.sub(pattern, f"urlpatterns = [\n{new_body}]", text, flags=re.DOTALL)

    urls_path.write_text(text, encoding="utf-8")
    print("Patched root urls.py to include scalability_core URLs at /api/system/.")


def main():
    manage_py = find_manage_py()
    settings_module = detect_settings_module(manage_py)

    print(f"Detected settings module: {settings_module}")

    ensure_scalability_app()
    patch_settings(settings_module)
    ensure_celery_py(settings_module)
    patch_urls(settings_module)

    print("\n=== DONE ===")
    print("Now run:")
    print("  pip install celery redis djangorestframework boto3 requests django-redis django-celery-beat django-celery-results")
    print("  python manage.py makemigrations scalability_core")
    print("  python manage.py migrate")
    print("\nEnvironment variables you should set for production:")
    print("  FCM_SERVER_KEY       # Firebase server key for FCM")
    print("  REDIS_URL            # redis://host:port/db")
    print("  CELERY_BROKER_URL    # optional, defaults to REDIS_URL")
    print("  CELERY_RESULT_BACKEND# optional, defaults to REDIS_URL")
    print("  FILE_UPLOAD_BUCKET   # S3 bucket for presigned uploads")
    print("\nThis gives you:")
    print("  - FCM command + ACK pipeline")
    print("  - Device registration + audit logs + location pings models")
    print("  - Celery tasks + Redis cache + DRF throttling")
    print("  - /api/system/devices/ack/ and /api/system/uploads/presign/ and /api/system/health/")


if __name__ == "__main__":
    main()
