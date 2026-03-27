from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.cache import cache

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from .models import Device, AuditLog, EnrollmentToken, Customer
from .serializers import DeviceHeartbeatSerializer, DPCEnrollSerializer
from .permissions import IsDPCClient
from .utils import generate_s3_presigned_url, send_fcm_to_manager, send_fcm_to_owner, send_fcm

from scalability_core.models import DeviceRegistration

import secrets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from manager.models import ManagerProfile


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def auth_me(request):

    user = request.user

    manager_profile = ManagerProfile.objects.filter(user=user).first()

    is_owner = user.is_superuser or user.is_staff
    is_manager = manager_profile is not None

    return Response({
        "username": user.username,
        "is_owner": is_owner,
        "is_manager": is_manager,
        "manager_id": manager_profile.id if manager_profile else None
    })
# =========================================================
# DEVICE HEARTBEAT
# =========================================================

class DeviceHeartbeatView(APIView):
    """
    /api/dpc/heartbeat/
    DPC client sends SIM + location + its FCM token periodically.
    """

    permission_classes = [IsDPCClient]

    def post(self, request):

        serializer = DeviceHeartbeatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        imei1 = data["imei1"]

        # ⚡ faster query
        device = (
            Device.objects
            .select_related("customer", "customer__manager", "device_registration")
            .filter(imei1=imei1)
            .first()
        )

        if not device:
            return Response(
                {"detail": "Device not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        customer = device.customer
        manager_profile = customer.manager

        old_sim1 = device.sim1_number
        old_sim2 = device.sim2_number

        # --------------------------
        # SIM update
        # --------------------------

        if "sim1_number" in data:
            device.sim1_number = data.get("sim1_number") or device.sim1_number

        if "sim2_number" in data:
            device.sim2_number = data.get("sim2_number") or device.sim2_number

        # --------------------------
        # Location update
        # --------------------------

        if "lat" in data and "lng" in data:

            device.last_location_lat = data["lat"]
            device.last_location_lng = data["lng"]
            device.last_location_time = timezone.now()

            AuditLog.objects.create(
                customer=customer,
                device=device,
                manager=manager_profile,
                action=AuditLog.ACTION_UPDATE_LOCATION,
                status=AuditLog.STATUS_SUCCESS,
                payload={
                    "lat": device.last_location_lat,
                    "lng": device.last_location_lng,
                },
            )

        # --------------------------
        # FCM token update
        # --------------------------

        if data.get("fcm_token"):
            device.dpc_fcm_token = data["fcm_token"]

        device.last_seen_at = timezone.now()
        device.save()

        # --------------------------
        # Redis online tracking
        # --------------------------

        cache.set(
            f"device_online:{device.imei1}",
            True,
            timeout=120
        )

        # --------------------------
        # Sync DeviceRegistration
        # --------------------------

        dr = device.device_registration

        if not dr:
            dr = DeviceRegistration.objects.filter(imei_1=device.imei1).first()

        if dr:

            dr.fcm_token = device.dpc_fcm_token or dr.fcm_token
            dr.last_seen = timezone.now()
            dr.last_ip = request.META.get("REMOTE_ADDR")
            dr.is_active = True

            dr.save(
                update_fields=[
                    "fcm_token",
                    "last_seen",
                    "last_ip",
                    "is_active"
                ]
            )

        else:

            dr = DeviceRegistration.objects.create(
                user=manager_profile.user,
                manager_id=manager_profile.id,
                imei_1=device.imei1,
                imei_2=device.imei2,
                device_id=device.imei1,
                fcm_token=device.dpc_fcm_token or "",
                device_token=secrets.token_hex(32),
                last_seen=timezone.now(),
                is_active=True,
            )

            device.device_registration = dr
            device.save(update_fields=["device_registration"])

        # --------------------------
        # SIM change detection
        # --------------------------

        if (
            (old_sim1 and device.sim1_number and old_sim1 != device.sim1_number)
            or
            (old_sim2 and device.sim2_number and old_sim2 != device.sim2_number)
        ):

            log = AuditLog.objects.create(
                customer=customer,
                device=device,
                manager=manager_profile,
                action=AuditLog.ACTION_SIM_CHANGE,
                status=AuditLog.STATUS_SUCCESS,
                payload={
                    "old_sim1": old_sim1,
                    "new_sim1": device.sim1_number,
                    "old_sim2": old_sim2,
                    "new_sim2": device.sim2_number,
                },
            )

            msg_title = "SIM changed"
            msg_body = f"User {customer.name} (IMEI {device.imei1}) SIM changed."

            send_fcm_to_manager(
                manager_profile,
                msg_title,
                msg_body,
                data={"audit_log_id": log.id, "customer_id": customer.id},
            )

            send_fcm_to_owner(
                msg_title,
                msg_body,
                data={"audit_log_id": log.id, "customer_id": customer.id},
            )

        return Response(
            {"detail": "Heartbeat updated."},
            status=status.HTTP_200_OK
        )


# =========================================================
# DEVICE ENROLL
# =========================================================

class DPCEnrollView(APIView):
    """
    /api/dpc/enroll/
    Called by DPC when scanning QR.
    """

    permission_classes = [IsDPCClient]

    def post(self, request):

        serializer = DPCEnrollSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        token_str = data["token"]
        manager_id = data["manager_id"]
        imei1 = data["imei1"]

        et = get_object_or_404(
            EnrollmentToken,
            token=token_str,
            status=EnrollmentToken.STATUS_ACTIVE,
        )

        # 🔒 token expiration protection
        if et.expires_at and et.expires_at < timezone.now():
            et.status = EnrollmentToken.STATUS_EXPIRED
            et.save(update_fields=["status"])

            return Response(
                {"detail": "Enrollment token expired"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if et.manager_id != manager_id:
            return Response(
                {"detail": "Invalid manager for token"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        customer = et.customer
        device = get_object_or_404(Device, customer=customer)

        if device.imei1 != imei1:
            return Response(
                {"detail": "IMEI mismatch"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if data.get("imei2"):
            device.imei2 = data["imei2"]

        if data.get("fcm_token"):
            device.dpc_fcm_token = data["fcm_token"]

        device.dpc_status = Device.DPC_STATUS_ENROLLED
        device.last_seen_at = timezone.now()
        device.save()

        manager_profile = customer.manager

        dr, created = DeviceRegistration.objects.update_or_create(
            imei_1=device.imei1,
            defaults={
                "user": manager_profile.user,
                "manager_id": manager_profile.id,
                "imei_2": device.imei2,
                "device_id": data.get("device_id") or device.imei1,
                "fcm_token": device.dpc_fcm_token or "",
                "device_token": secrets.token_hex(32),
                "last_seen": timezone.now(),
                "is_active": True,
            },
        )

        device.device_registration = dr
        device.save(update_fields=["device_registration"])

        et.status = EnrollmentToken.STATUS_USED
        et.save(update_fields=["status"])

        log = AuditLog.objects.create(
            customer=customer,
            device=device,
            manager=manager_profile,
            action=AuditLog.ACTION_ENROLL_USER,
            status=AuditLog.STATUS_SUCCESS,
            payload={"token": token_str},
        )

        title = "New device enrolled"
        body = f"User {customer.name} (IMEI {device.imei1}) enrolled successfully."

        send_fcm_to_manager(manager_profile, title, body, data={"audit_log_id": log.id})
        send_fcm_to_owner(title, body, data={"audit_log_id": log.id})

        return Response(
            {"detail": "Enroll success."},
            status=status.HTTP_200_OK
        )
# =========================================================
# LOCK STATUS ACK
# =========================================================

class DPCLockStatusAckView(APIView):

    permission_classes = [IsDPCClient]

    def post(self, request):

        imei1 = request.data.get("imei1")
        locked = request.data.get("locked")

        device = Device.objects.filter(imei1=imei1).first()

        if not device:
            return Response(
                {"detail": "Device not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        device.is_locked = locked
        device.save(update_fields=["is_locked"])

        AuditLog.objects.create(
            customer=device.customer,
            device=device,
            manager=device.customer.manager,
            action=AuditLog.ACTION_LOCK_DEVICE,
            status=AuditLog.STATUS_SUCCESS,
            payload={"locked": locked},
        )

        return Response(
            {"detail": "Lock status updated"},
            status=status.HTTP_200_OK,
        )


# =========================================================
# S3 UPLOAD URL
# =========================================================

class S3UploadUrlView(APIView):

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):

        filename = request.data.get("filename")

        if not filename:
            return Response(
                {"detail": "filename required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        url = generate_s3_presigned_url(filename)

        return Response({"upload_url": url})


# =========================================================
# DPC UNENROLL ACK
# =========================================================

class DPCUnenrollAckView(APIView):

    permission_classes = [IsDPCClient]

    def post(self, request):

        imei1 = request.data.get("imei1")

        device = Device.objects.filter(imei1=imei1).first()

        if not device:
            return Response(
                {"detail": "Device not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        device.dpc_status = Device.DPC_STATUS_UNENROLLED
        device.last_seen_at = timezone.now()
        device.save(update_fields=["dpc_status", "last_seen_at"])

        return Response(
            {"detail": "Unenroll acknowledged"},
            status=status.HTTP_200_OK,
        )