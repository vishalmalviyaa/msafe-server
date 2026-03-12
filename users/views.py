from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from .models import Device, AuditLog, EnrollmentToken, Customer
from .serializers import DeviceHeartbeatSerializer, DPCEnrollSerializer
from .permissions import IsDPCClient
from .utils import generate_s3_presigned_url, send_fcm_to_manager, send_fcm_to_owner, send_fcm

from scalability_core.models import DeviceRegistration
import secrets
from django.core.cache import cache
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
        device = get_object_or_404(Device, imei1=imei1)
        customer = device.customer
        manager_profile = customer.manager

        old_sim1 = device.sim1_number
        old_sim2 = device.sim2_number

        # Update SIM numbers
        if "sim1_number" in data:
            device.sim1_number = data.get("sim1_number") or device.sim1_number
        if "sim2_number" in data:
            device.sim2_number = data.get("sim2_number") or device.sim2_number

        # Location
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

        # FCM token
        if data.get("fcm_token"):
            device.dpc_fcm_token = data["fcm_token"]

        device.last_seen_at = timezone.now()
        device.save()

        # Sync into scalability_core.DeviceRegistration
        dr = device.device_registration
        if not dr:
            dr = DeviceRegistration.objects.filter(imei_1=device.imei1).first()

        if dr:
            # Update existing device registration
            dr.fcm_token = device.dpc_fcm_token or dr.fcm_token
            dr.last_seen = timezone.now()
            dr.is_active = True
            dr.save(update_fields=["fcm_token", "last_seen", "is_active"])
        else:
            # Create if missing
            dr = DeviceRegistration.objects.create(
                user=manager_profile.user,
                manager_id=manager_profile.id,
                imei_1=device.imei1,
                imei_2=device.imei2,
                device_id=device.imei1,
                fcm_token=device.dpc_fcm_token or "",
                last_seen=timezone.now(),
                is_active=True,
            )
            device.device_registration = dr
            device.save(update_fields=["device_registration"])

        # SIM change detection
        if (old_sim1 and device.sim1_number and old_sim1 != device.sim1_number) or \
           (old_sim2 and device.sim2_number and old_sim2 != device.sim2_number):

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

        return Response({"detail": "Heartbeat updated."}, status=status.HTTP_200_OK)


class DPCUnenrollAckView(APIView):
    """
    /api/dpc/unenroll_ack/
    DPC calls this after performing UNENROLL (self-removal).

    Body:
    {
        "imei1": "...",
        "status": "SUCCESS" | "FAILED",
        "audit_log_id": 123   # optional but recommended
    }
    """
    permission_classes = [IsDPCClient]

    def post(self, request):
        imei1 = request.data.get("imei1")
        status_str = request.data.get("status", "SUCCESS")
        audit_log_id = request.data.get("audit_log_id")

        if not imei1:
            return Response({"detail": "imei1 required"}, status=status.HTTP_400_BAD_REQUEST)

        device = get_object_or_404(Device, imei1=imei1)
        customer = device.customer
        manager_profile = customer.manager

        if status_str.upper() == "SUCCESS":
            device.dpc_status = Device.DPC_STATUS_UNENROLLED
            device.lock_status = Device.LOCK_STATUS_UNLOCKED
            device.save(update_fields=["dpc_status", "lock_status"])

            # soft deactivate customer
            customer.is_active = False
            customer.save(update_fields=["is_active"])

            # Resolve pending DELETE_USER audit if we know which one
            if audit_log_id:
                try:
                    pending = AuditLog.objects.get(
                        id=audit_log_id,
                        customer=customer,
                        device=device,
                        manager=manager_profile,
                        action=AuditLog.ACTION_DELETE_USER,
                        status=AuditLog.STATUS_PENDING,
                    )
                    pending.status = AuditLog.STATUS_SUCCESS
                    payload = pending.payload or {}
                    payload["unenroll_ack"] = True
                    payload["ack_payload"] = request.data
                    pending.payload = payload
                    pending.save(update_fields=["status", "payload"])
                except AuditLog.DoesNotExist:
                    pass

            # Optional: also add a final SUCCESS log
            log = AuditLog.objects.create(
                customer=customer,
                device=device,
                manager=manager_profile,
                action=AuditLog.ACTION_DELETE_USER,
                status=AuditLog.STATUS_SUCCESS,
                payload={"unenroll_ack": True},
            )

            title = "User unenrolled"
            body = f"User {customer.name} (IMEI {device.imei1}) unenrolled and DPC removed."
            send_fcm_to_manager(manager_profile, title, body, data={"audit_log_id": log.id})
            send_fcm_to_owner(title, body, data={"audit_log_id": log.id})

            return Response({"detail": "Unenroll confirmed."}, status=status.HTTP_200_OK)

        # Failed unenroll
        device.dpc_status = Device.DPC_STATUS_ENROLLED
        device.save(update_fields=["dpc_status"])


        # Mark pending DELETE_USER as FAILED if present
        if audit_log_id:
            try:
                pending = AuditLog.objects.get(
                    id=audit_log_id,
                    customer=customer,
                    device=device,
                    manager=manager_profile,
                    action=AuditLog.ACTION_DELETE_USER,
                    status=AuditLog.STATUS_PENDING,
                )
                pending.status = AuditLog.STATUS_FAILED
                payload = pending.payload or {}
                payload["reason"] = "Device reported unenroll failure."
                payload["ack_payload"] = request.data
                pending.payload = payload
                pending.save(update_fields=["status", "payload"])
            except AuditLog.DoesNotExist:
                pass

        log = AuditLog.objects.create(
            customer=customer,
            device=device,
            manager=manager_profile,
            action=AuditLog.ACTION_DELETE_USER,
            status=AuditLog.STATUS_FAILED,
            payload={"reason": "Device reported unenroll failure."},
        )

        title = "User unenroll failed"
        body = f"User {customer.name} (IMEI {device.imei1}) unenroll FAILED."
        send_fcm_to_manager(manager_profile, title, body, data={"audit_log_id": log.id})
        send_fcm_to_owner(title, body, data={"audit_log_id": log.id})

        return Response({"detail": "Unenroll failed."}, status=status.HTTP_200_OK)


class DPCLockStatusAckView(APIView):
    """
    /api/dpc/lock_status_ack/
    Body: { imei1, status: "LOCKED" | "UNLOCKED", audit_log_id? }
    DPC tells backend that lock/unlock actually applied.
    """
    permission_classes = [IsDPCClient]

    def post(self, request):
        imei1 = request.data.get("imei1")
        status_str = request.data.get("status")
        audit_log_id = request.data.get("audit_log_id")

        if not imei1 or status_str not in ["LOCKED", "UNLOCKED"]:
            return Response(
                {"detail": "imei1 and valid status required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        device = get_object_or_404(Device, imei1=imei1)
        customer = device.customer
        manager_profile = customer.manager

        # Update device lock_status
        if status_str == "LOCKED":
            device.lock_status = Device.LOCK_STATUS_LOCKED
        else:
            device.lock_status = Device.LOCK_STATUS_UNLOCKED
        device.save(update_fields=["lock_status"])

        # Try to resolve existing pending audit log
        log = None
        if audit_log_id:
            try:
                log = AuditLog.objects.get(
                    id=audit_log_id,
                    customer=customer,
                    device=device,
                    manager=manager_profile,
                    action__in=[AuditLog.ACTION_LOCK_USER, AuditLog.ACTION_UNLOCK_USER],
                )
                log.status = AuditLog.STATUS_SUCCESS
                payload = log.payload or {}
                payload["lock_status"] = status_str
                log.payload = payload
                log.save(update_fields=["status", "payload"])
            except AuditLog.DoesNotExist:
                log = None

        # Fallback: create new SUCCESS log if needed
        if log is None:
            action = (
                AuditLog.ACTION_LOCK_USER
                if status_str == "LOCKED"
                else AuditLog.ACTION_UNLOCK_USER
            )
            log = AuditLog.objects.create(
                customer=customer,
                device=device,
                manager=manager_profile,
                action=action,
                status=AuditLog.STATUS_SUCCESS,
                payload={"lock_status": status_str},
            )

        title = f"Device {status_str.lower()}"
        body = f"User {customer.name} (IMEI {device.imei1}) is now {status_str.lower()}."
        send_fcm_to_manager(manager_profile, title, body, data={"audit_log_id": log.id})
        send_fcm_to_owner(title, body, data={"audit_log_id": log.id})

        return Response({"detail": "Lock status updated."}, status=status.HTTP_200_OK)


class DPCEnrollView(APIView):
    """
    /api/dpc/enroll/
    Called by DPC when scanning QR with {token, manager_id, imei1, imei2?, fcm_token?, device_id?}.
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
        if et.manager_id != manager_id:
            return Response({"detail": "Invalid manager for token."}, status=status.HTTP_400_BAD_REQUEST)

        customer = et.customer
        device = get_object_or_404(Device, customer=customer)

        if device.imei1 != imei1:
            return Response({"detail": "IMEI mismatch."}, status=status.HTTP_400_BAD_REQUEST)

        if data.get("imei2"):
            device.imei2 = data["imei2"]
        if data.get("fcm_token"):
            device.dpc_fcm_token = data["fcm_token"]

        device.dpc_status = Device.DPC_STATUS_ENROLLED
        device.last_seen_at = timezone.now()
        device.save()

        # Upsert into DeviceRegistration
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
            manager=customer.manager,
            action=AuditLog.ACTION_ENROLL_USER,
            status=AuditLog.STATUS_SUCCESS,
            payload={"token": token_str},
        )

        title = "New device enrolled"
        body = f"User {customer.name} (IMEI {device.imei1}) enrolled successfully."
        send_fcm_to_manager(customer.manager, title, body, data={"audit_log_id": log.id})
        send_fcm_to_owner(title, body, data={"audit_log_id": log.id})

        return Response({"detail": "Enroll success."}, status=status.HTTP_200_OK)


class S3UploadUrlView(APIView):
    """
    /api/uploads/url/
    Returns a presigned S3 URL to upload a file (photo or signature).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        file_name = request.data.get("file_name")
        content_type = request.data.get("content_type", "image/jpeg")
        folder = request.data.get("folder", "misc")

        if not file_name:
            return Response({"detail": "file_name required"}, status=status.HTTP_400_BAD_REQUEST)

        import uuid
        ext = file_name.split(".")[-1]
        key = f"{folder}/{uuid.uuid4()}.{ext}"

        try:
            upload_url, final_url = generate_s3_presigned_url(key, content_type)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(
            {
                "upload_url": upload_url,
                "file_url": final_url,
            },
            status=status.HTTP_200_OK,
        )
