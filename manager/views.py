import secrets
import qrcode
from io import BytesIO
from datetime import timedelta
import json
from django.http import HttpResponse
from django.utils import timezone
from django.core.cache import cache

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
from django.http import FileResponse, HttpResponse
from django.conf import settings
import os



# =========================================================
# CUSTOMER MANAGEMENT
# =========================================================

class ManagerCustomerViewSet(viewsets.ModelViewSet):

    permission_classes = [IsAuthenticated, IsManager, IsManagerOfCustomer]

    filter_backends = [filters.SearchFilter, filters.OrderingFilter]

    search_fields = ["name", "phone", "device__imei1", "device__imei2"]

    ordering_fields = ["created_at", "name"]


    # -----------------------------------------------------
    # QR PROVISIONING
    # -----------------------------------------------------

    @action(detail=True, methods=["get"])
    def qr_png(self, request, pk=None):

        customer = self.get_object()
        device = getattr(customer, "device", None)

        if not device:
            return Response(
                {"detail": "No device linked."},
                status=status.HTTP_400_BAD_REQUEST
            )

        manager_profile = request.user.manager_profile

        token = (
            EnrollmentToken.objects
            .filter(customer=customer)
            .order_by("-created_at")
            .first()
        )

        if not token:
            return Response(
                {"detail": "Enrollment token not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        payload = {

    "android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME":
    "com.vashu.msafe.agent/.AdminReceiver",

    "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION":
    "https://api.msafe.shop/api/manager/download/msafe-agent.apk",

    "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_CHECKSUM":
    "BAAB5D65DE30674600CCFB2D28D2526C8B459885C76042D4857CD621602B7AFE",

    "android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE": {

        "token": token.token,
        "manager_id": manager_profile.id,
        "imei1": device.imei1
    }
}

        qr = qrcode.make(json.dumps(payload))

        buffer = BytesIO()
        qr.save(buffer)

        response = HttpResponse(
            buffer.getvalue(),
            content_type="image/png"
        )  

        response["Cache-Control"] = "no-store"
        return response

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


    # -----------------------------------------------------

    def create(self, request, *args, **kwargs):

        manager_profile = request.user.manager_profile

        if manager_profile.keys_remaining() <= 0:

            return Response(
                {"detail": "No enrollment keys left."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(
            data=request.data,
            context={"request": request},
        )

        serializer.is_valid(raise_exception=True)

        customer = serializer.save()

        token_str = secrets.token_urlsafe(32)

        EnrollmentToken.objects.create(
            token=token_str,
            manager=manager_profile,
            customer=customer,
        )

        manager_profile.used_keys += 1
        manager_profile.save(update_fields=["used_keys"])

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


# =========================================================
# LOCK DEVICE
# =========================================================

    @action(detail=True, methods=["post"])

    def lock(self, request, pk=None):

        customer = self.get_object()

        device = getattr(customer, "device", None)

        if not device:

            return Response(
                {"detail": "No device linked."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        manager_profile = request.user.manager_profile

        lock_message = (
            request.data.get("message")
            or manager_profile.default_lock_message
        )

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

        reg, _ = DeviceRegistration.objects.update_or_create(
            imei_1=device.imei1,
            defaults={
                "imei_2": device.imei2 or "",
                "fcm_token": device.dpc_fcm_token or "",
                "manager_id": manager_profile.id,
                "device_id": device.imei1,
                "user": manager_profile.user,
            },
        )

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

        send_fcm_command_task.delay(cmd.id)

        title = "Lock requested"

        body = f"Lock requested for {customer.name} (IMEI {device.imei1})."

        send_fcm_to_manager(
            manager_profile,
            title,
            body,
            data={"audit_log_id": log.id},
        )

        send_fcm_to_owner(title, body, data={"audit_log_id": log.id})

        return Response(
            {"detail": "Lock command queued."},
            status=status.HTTP_202_ACCEPTED,
        )


# =========================================================
# UNLOCK DEVICE
# =========================================================

    @action(detail=True, methods=["post"])

    def unlock(self, request, pk=None):

        customer = self.get_object()

        device = getattr(customer, "device", None)

        if not device:

            return Response(
                {"detail": "No device linked."},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
                "device_id": device.imei1,
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

        return Response(
            {"detail": "Unlock command queued."},
            status=status.HTTP_202_ACCEPTED,
        )


# =========================================================
# UNENROLL DEVICE
# =========================================================

    @action(detail=True, methods=["post"])

    def delete_user(self, request, pk=None):

        customer = self.get_object()

        device = getattr(customer, "device", None)

        if not device:

            return Response(
                {"detail": "No device linked."},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
                "device_id": device.imei1,
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

        return Response(
            {"detail": "Unenroll command queued."},
            status=status.HTTP_202_ACCEPTED,
        )


# =========================================================
# MANAGER PROFILE
# =========================================================

class ManagerProfileViewSet(viewsets.ViewSet):

    permission_classes = [IsAuthenticated, IsManager]


    def get_object(self):

        return self.request.user.manager_profile


    def list(self, request):

        profile = self.get_object()

        serializer = ManagerProfileSerializer(profile)

        return Response(serializer.data)


    def partial_update(self, request, pk=None):

        profile = self.get_object()

        serializer = ManagerProfileSerializer(
            profile,
            data=request.data,
            partial=True,
        )

        serializer.is_valid(raise_exception=True)

        serializer.save()

        return Response(serializer.data)


# =========================================================
# MANAGER DEVICE REGISTRATION
# =========================================================

class ManagerRegisterDeviceView(APIView):

    permission_classes = [IsAuthenticated, IsManager]


    def post(self, request):

        fcm_token = request.data.get("fcm_token")

        if not fcm_token:

            return Response(
                {"detail": "fcm_token required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile = request.user.manager_profile

        profile.fcm_token = fcm_token

        profile.save(update_fields=["fcm_token"])

        return Response(
            {
                "detail": "Manager device registered.",
                "manager_id": profile.id,
                "fcm_token": profile.fcm_token,
            }
        )


# =========================================================
# MANAGER DASHBOARD
# =========================================================

class ManagerDashboardView(APIView):

    permission_classes = [IsAuthenticated, IsManager]


    def get(self, request):

        manager = request.user.manager_profile

        devices = (
            Device.objects
            .filter(customer__manager=manager)
            .select_related("customer", "device_registration")
        )

        result = []

        for device in devices:

            reg = device.device_registration

            battery = None

            online = False

            location = None

            if reg:

                battery = getattr(reg, "battery_level", None)

                online = cache.get(f"device_online:{reg.device_id}") or False

                loc = cache.get(f"device_location:{reg.device_id}")

                if loc:
                    location = loc

            result.append(
                {
                    "device_id": device.imei1,
                    "customer": device.customer.name,
                    "phone": device.customer.phone,
                    "battery": battery,
                    "online": online,
                    "lock_status": device.lock_status,
                    "location": location,
                }
            )

        return Response(result)
class ManagerDeviceMapView(APIView):

    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):

        manager = request.user.manager_profile

        devices = (
            Device.objects
            .filter(customer__manager=manager)
            .select_related("customer", "device_registration")
        )

        results = []

        for device in devices:

            reg = device.device_registration

            if not reg:
                continue

            loc = cache.get(f"device_location:{reg.device_id}")

            if not loc:
                continue

            online = cache.get(f"device_online:{reg.device_id}") or False

            results.append({
                "imei": device.imei1,
                "name": device.customer.name,
                "phone": device.customer.phone,
                "lat": loc["lat"],
                "lng": loc["lng"],
                "battery": reg.battery_level,
                "online": online
            })

        return Response(results)
from django.http import FileResponse, Http404
from django.conf import settings
import os



def download_agent(request):

    file_path = os.path.join(settings.BASE_DIR, "download", "msafe-agent.apk")

    if not os.path.exists(file_path):
        return HttpResponse(f"File not found: {file_path}")

    try:
        return FileResponse(
            open(file_path, "rb"),
            content_type="application/vnd.android.package-archive"
        )
    except Exception as e:
        return HttpResponse(f"Error opening file: {str(e)}")