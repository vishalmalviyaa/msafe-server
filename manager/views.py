import secrets
import qrcode
from io import BytesIO

from django.http import HttpResponse

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from users.models import Customer, Device, AuditLog, EnrollmentToken
from users.serializers import CustomerSerializer, CustomerCreateUpdateSerializer
from users.permissions import IsManagerOfCustomer
from users.utils import send_fcm_to_manager, send_fcm_to_owner

from .models import ManagerProfile
from .serializers import ManagerProfileSerializer
from .permissions import IsManager

from scalability_core.models import DeviceRegistration, FcmCommand
from scalability_core.tasks import send_fcm_command_task


class ManagerCustomerViewSet(viewsets.ModelViewSet):
    """
    /api/manager/users/
    Manager can add/edit/view their own customers.
    On create -> generates EnrollmentToken and returns QR payload info.
    """
    permission_classes = [IsAuthenticated, IsManager, IsManagerOfCustomer]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "phone", "device__imei1", "device__imei2"]
    ordering_fields = ["created_at", "name"]

    def get_queryset(self):
        manager_profile = self.request.user.manager_profile
        return (
            Customer.objects
            .filter(manager=manager_profile, is_active=True)
            .select_related("device")
        )

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return CustomerCreateUpdateSerializer
        return CustomerSerializer

    def create(self, request, *args, **kwargs):
        manager_profile = self.request.user.manager_profile

        if manager_profile.keys_remaining() <= 0:
            return Response(
                {"detail": "No enrollment keys left."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        customer = serializer.save()

        # create enrollment token
        token_str = secrets.token_urlsafe(32)
        EnrollmentToken.objects.create(
            token=token_str,
            manager=manager_profile,
            customer=customer,
        )

        # update used keys
        manager_profile.used_keys += 1
        manager_profile.save(update_fields=["used_keys"])

        # for QR: token + manager_id + imei1
        device = customer.device
        qr_payload = {
            "token": token_str,
            "manager_id": manager_profile.id,
            "imei1": device.imei1,
        }

        customer_data = CustomerSerializer(customer).data
        headers = self.get_success_headers(customer_data)
        return Response(
            {
                "customer": customer_data,
                "enrollment": qr_payload,
            },
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        """
        Manager requests LOCK.
        Creates FcmCommand and lets Celery send FCM.
        DPC will ACK via /api/system/devices/ack/ and
        scalability_core.tasks.reconcile_command_ack_task
        will finalize Device.lock_status + AuditLog.
        """
        customer = self.get_object()
        device = getattr(customer, "device", None)
        if not device:
            return Response({"detail": "No device linked."}, status=status.HTTP_400_BAD_REQUEST)

        manager_profile = request.user.manager_profile

        # Use manager default lock message + optional override
        lock_message = request.data.get("message") or manager_profile.default_lock_message
        logo_url = request.data.get("logo_url") or ""

        device.lock_status = Device.LOCK_STATUS_PENDING_LOCK
        device.save(update_fields=["lock_status"])

        log = AuditLog.objects.create(
            manager=manager_profile,
            customer=customer,
            device=device,
            action=AuditLog.ACTION_LOCK_USER,
            status=AuditLog.STATUS_PENDING,
            payload={"message": lock_message, "logo_url": logo_url},
        )

        # Ensure DeviceRegistration exists
        reg, _ = DeviceRegistration.objects.update_or_create(
            imei_1=device.imei1,
            defaults={
                "imei_2": device.imei2 or "",
                "fcm_token": device.dpc_fcm_token or "",
                "manager_id": manager_profile.id,
                "device_id": str(device.id),
                "user": manager_profile.user,
            },
        )

        # Create FcmCommand
        cmd = FcmCommand.objects.create(
            device=reg,
            action="LOCK",
            payload={
                "audit_log_id": log.id,
                "customer_id": customer.id,
                "device_id": device.id,
                "manager_id": manager_profile.id,
                "message": lock_message,
                "logo_url": logo_url,
            },
        )

        # Send via Celery
        send_fcm_command_task.delay(cmd.id)

        title = "Lock requested"
        body = f"Lock requested for {customer.name} (IMEI {device.imei1})."
        send_fcm_to_manager(manager_profile, title, body, data={"audit_log_id": log.id})
        send_fcm_to_owner(title, body, data={"audit_log_id": log.id})

        return Response({"detail": "Lock command queued."}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def unlock(self, request, pk=None):
        """
        Same flow as lock but for UNLOCK.
        """
        customer = self.get_object()
        device = getattr(customer, "device", None)
        if not device:
            return Response({"detail": "No device linked."}, status=status.HTTP_400_BAD_REQUEST)

        manager_profile = request.user.manager_profile

        device.lock_status = Device.LOCK_STATUS_PENDING_UNLOCK
        device.save(update_fields=["lock_status"])

        log = AuditLog.objects.create(
            manager=manager_profile,
            customer=customer,
            device=device,
            action=AuditLog.ACTION_UNLOCK_USER,
            status=AuditLog.STATUS_PENDING,
        )

        reg, _ = DeviceRegistration.objects.update_or_create(
            imei_1=device.imei1,
            defaults={
                "imei_2": device.imei2 or "",
                "fcm_token": device.dpc_fcm_token or "",
                "manager_id": manager_profile.id,
                "device_id": str(device.id),
                "user": manager_profile.user,
            },
        )

        cmd = FcmCommand.objects.create(
            device=reg,
            action="UNLOCK",
            payload={
                "audit_log_id": log.id,
                "customer_id": customer.id,
                "device_id": device.id,
                "manager_id": manager_profile.id,
            },
        )
        send_fcm_command_task.delay(cmd.id)

        title = "Unlock requested"
        body = f"Unlock requested for {customer.name} (IMEI {device.imei1})."
        send_fcm_to_manager(manager_profile, title, body, data={"audit_log_id": log.id})
        send_fcm_to_owner(title, body, data={"audit_log_id": log.id})

        return Response({"detail": "Unlock command queued."}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def delete_user(self, request, pk=None):
        """
        Manager triggers UNENROLL for this customer.
        This will cause DPC to uninstall itself and send ACK.
        """
        customer = self.get_object()
        device = getattr(customer, "device", None)
        if not device:
            return Response({"detail": "No device linked."}, status=status.HTTP_400_BAD_REQUEST)

        manager_profile = request.user.manager_profile

        device.dpc_status = Device.DPC_STATUS_UNENROLL_PENDING
        device.save(update_fields=["dpc_status"])

        log = AuditLog.objects.create(
            manager=manager_profile,
            customer=customer,
            device=device,
            action=AuditLog.ACTION_DELETE_USER,
            status=AuditLog.STATUS_PENDING,
        )

        reg, _ = DeviceRegistration.objects.update_or_create(
            imei_1=device.imei1,
            defaults={
                "imei_2": device.imei2 or "",
                "fcm_token": device.dpc_fcm_token or "",
                "manager_id": manager_profile.id,
                "device_id": str(device.id),
                "user": manager_profile.user,
            },
        )

        cmd = FcmCommand.objects.create(
            device=reg,
            action="UNENROLL",
            payload={
                "audit_log_id": log.id,
                "customer_id": customer.id,
                "device_id": device.id,
                "manager_id": manager_profile.id,
                "forced_by_owner": False,
            },
        )
        send_fcm_command_task.delay(cmd.id)

        title = "User unenroll requested"
        body = f"Unenroll requested for {customer.name} (IMEI {device.imei1})."
        send_fcm_to_manager(manager_profile, title, body, data={"audit_log_id": log.id})
        send_fcm_to_owner(title, body, data={"audit_log_id": log.id})

        return Response(
            {"detail": "Unenroll command queued.", "audit_log_id": log.id},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"])
    def share_text(self, request, pk=None):
        """
        Returns preformatted WhatsApp share text for this user (Manager side).
        """
        customer = self.get_object()
        device = getattr(customer, "device", None)

        lines = [
            "User Details:",
            f"Name: {customer.name}",
            f"Phone: {customer.phone}",
        ]

        if device:
            lines.append(f"IMEI1: {device.imei1}")
            if device.imei2:
                lines.append(f"IMEI2: {device.imei2}")
            if device.sim1_number:
                lines.append(f"SIM1: {device.sim1_number}")
            if device.sim2_number:
                lines.append(f"SIM2: {device.sim2_number}")
            if device.last_location_lat and device.last_location_lng:
                loc_url = f"https://maps.google.com/?q={device.last_location_lat},{device.last_location_lng}"
                lines.append(f"Location: {loc_url}")

        text = "\n".join(lines)
        return Response({"text": text}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def qr_png(self, request, pk=None):
        """
        /api/manager/users/{id}/qr_png/
        Returns QR code PNG for enrollment payload (token+manager_id+imei1).
        """
        customer = self.get_object()
        device = customer.device
        manager_profile = request.user.manager_profile

        et = (
            EnrollmentToken.objects
            .filter(customer=customer, manager=manager_profile)
            .order_by("-created_at")
            .first()
        )
        if not et:
            return Response({"detail": "Enrollment token not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = {
            "token": et.token,
            "manager_id": manager_profile.id,
            "imei1": device.imei1,
        }

        img = qrcode.make(payload)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        return HttpResponse(buffer.getvalue(), content_type="image/png")


class ManagerProfileViewSet(viewsets.ViewSet):
    """
    /api/manager/profile/
    Manager can view/update their profile & default lock settings.
    """
    permission_classes = [IsAuthenticated, IsManager]

    def get_object(self):
        return self.request.user.manager_profile

    def list(self, request):
        profile = self.get_object()
        serializer = ManagerProfileSerializer(profile)
        return Response(serializer.data)

    def partial_update(self, request, pk=None):
        profile = self.get_object()
        serializer = ManagerProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ManagerRegisterDeviceView(APIView):
    """
    /api/manager/devices/register/
    Called by ManagerApp to register/update its FCM token.
    Stores token in ManagerProfile.fcm_token.
    """
    permission_classes = [IsAuthenticated, IsManager]

    def post(self, request):
        fcm_token = request.data.get("fcm_token")
        if not fcm_token:
            return Response({"detail": "fcm_token required"}, status=status.HTTP_400_BAD_REQUEST)

        profile: ManagerProfile = request.user.manager_profile
        profile.fcm_token = fcm_token
        profile.save(update_fields=["fcm_token"])

        return Response(
            {
                "detail": "Manager device registered.",
                "manager_id": profile.id,
                "fcm_token": profile.fcm_token,
            },
            status=status.HTTP_200_OK,
        )
from django.utils import timezone
from datetime import timedelta

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.models import Customer
from .permissions import IsManager


class ManagerDeviceDashboardView(APIView):
    """
    Returns device dashboard data for manager app.
    Shows device health, location, lock status.
    """

    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):

        manager_profile = request.user.manager_profile

        customers = (
            Customer.objects
            .filter(manager=manager_profile, is_active=True)
            .select_related("device")
        )

        devices = []
        now = timezone.now()

        for c in customers:

            device = getattr(c, "device", None)

            if not device:
                continue

            last_seen = device.last_seen
            online = False

            if last_seen:
                online = now - last_seen < timedelta(minutes=2)

            devices.append({
                "customer_id": c.id,
                "name": c.name,
                "phone": c.phone,
                "imei1": device.imei1,
                "imei2": device.imei2,
                "lock_status": device.lock_status,
                "battery": getattr(device, "battery", None),
                "online": online,
                "last_seen": last_seen,
                "latitude": getattr(device, "last_location_lat", None),
                "longitude": getattr(device, "last_location_lng", None),
            })

        return Response({"devices": devices})