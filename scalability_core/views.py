import os
import uuid

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    DeviceRegistration,
    FcmCommand,
    CommandAck,
    AuditLog,
    LocationPing,
)

from .permissions import IsOwnerOrManager

from .serializers import (
    CommandAckSerializer,
    PresignUploadRequestSerializer,
    PresignUploadResponseSerializer,
    LocationPingSerializer,
)

from .tasks import reconcile_command_ack_task
from .utils import get_s3_presigned_post


# ---------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------

@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):

    pending = FcmCommand.objects.filter(status="PENDING").count()
    sent = FcmCommand.objects.filter(status="SENT").count()
    acked = FcmCommand.objects.filter(status="ACKED").count()
    failed = FcmCommand.objects.filter(status="FAILED").count()

    return Response(
        {
            "status": "ok",
            "time": timezone.now().isoformat(),
            "fcm_commands": {
                "pending": pending,
                "sent": sent,
                "acked": acked,
                "failed": failed,
            },
        }
    )


# ---------------------------------------------------
# DEVICE REGISTER
# ---------------------------------------------------

class DeviceRegisterView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):

        imei_1 = request.data.get("imei_1")
        imei_2 = request.data.get("imei_2")
        device_id = request.data.get("device_id")
        fcm_token = request.data.get("fcm_token")

        if not device_id or not fcm_token:
            return Response(
                {"error": "device_id and fcm_token required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        obj, created = DeviceRegistration.objects.update_or_create(
            device_id=device_id,
            defaults={
                "imei_1": imei_1,
                "imei_2": imei_2,
                "fcm_token": fcm_token,
                "last_seen": timezone.now(),
                "is_active": True,
            },
        )

        return Response(
            {
                "registered": True,
                "device_id": obj.id,
            }
        )


# ---------------------------------------------------
# DEVICE HEARTBEAT
# ---------------------------------------------------

class DeviceHeartbeatView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):

        device_id = request.data.get("device_id")
        token = request.headers.get("X-DEVICE-TOKEN")

        try:
            device = DeviceRegistration.objects.get(
                device_id=device_id,
                device_token=token
            )
        except DeviceRegistration.DoesNotExist:
            return Response(
                {"error": "invalid device"},
                status=status.HTTP_403_FORBIDDEN,
            )

        device.last_seen = timezone.now()
        device.last_ip = request.META.get("REMOTE_ADDR")

        device.battery_level = request.data.get("battery")
        device.network_type = request.data.get("network")
        device.android_version = request.data.get("android_version")
        device.is_charging = request.data.get("charging")

        device.save(
            update_fields=[
                "last_seen",
                "last_ip",
                "battery_level",
                "network_type",
                "android_version",
                "is_charging",
            ]
        )

        return Response({"status": "ok"})


class DeviceLocationPingView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):

        serializer = LocationPingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ping = serializer.save()

        # cache latest location on device for fast dashboard queries
        device = ping.device

        device.last_latitude = ping.latitude
        device.last_longitude = ping.longitude
        device.last_location_time = ping.captured_at

        device.save(
            update_fields=[
                "last_latitude",
                "last_longitude",
                "last_location_time",
            ]
        )

        return Response({"ok": True})


# ---------------------------------------------------
# COMMAND ACK
# ---------------------------------------------------

class DeviceAckView(APIView):

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

        CommandAck.objects.create(
            command=command,
            status=status_str,
            raw_payload=data.get("payload") or {},
        )

        reconcile_command_ack_task.delay(command.id)

        return Response({"ok": True})


# ---------------------------------------------------
# S3 PRESIGNED UPLOAD
# ---------------------------------------------------

class PresignUploadView(APIView):

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