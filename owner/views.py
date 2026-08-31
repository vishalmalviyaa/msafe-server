from django.shortcuts import get_object_or_404

from rest_framework import viewsets, status, filters, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action

from .models import OwnerProfile, OwnerDevice
from .serializers import OwnerProfileSerializer

from manager.models import ManagerProfile
from manager.serializers import ManagerProfileSerializer

from users.models import Customer, Device, AuditLog
from users.serializers import CustomerSerializer
from users.utils import send_fcm_to_owner

from .permissions import IsOwner

from scalability_core.models import DeviceRegistration, FcmCommand
from scalability_core.tasks import send_fcm_command_task

class OwnerCustomerViewSet(viewsets.ReadOnlyModelViewSet):
    """
    /api/owner/users/
    Owner can list all customers across all managers.
    """
    queryset = Customer.objects.select_related("manager", "device")
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "phone", "device__imei1", "device__imei2", "manager__user__username"]
    ordering_fields = ["created_at", "name"]

    @action(detail=True, methods=["get"])
    def share_text(self, request, pk=None):
        """
        /api/owner/users/{id}/share_text/
        Returns preformatted WhatsApp share text for this user (Owner side).
        """
        customer = self.get_object()
        device = getattr(customer, "device", None)

        lines = [
            "User Details:",
            f"Name: {customer.name}",
            f"Phone: {customer.phone}",
            f"Manager: {customer.manager.user.username if customer.manager and customer.manager.user else ''}",
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


class OwnerManagerViewSet(viewsets.ModelViewSet):
    """
    /api/owner/managers/
    Owner can create/update managers and allocate keys.
    """
    queryset = ManagerProfile.objects.select_related("user")
    serializer_class = ManagerProfileSerializer
    permission_classes = [IsAuthenticated, IsOwner]

    @action(detail=True, methods=["post"], url_path="allocate_keys")
    def allocate_keys(self, request, pk=None):
        """
        POST /api/owner/managers/{id}/allocate_keys/
        Body: {"keys": 10}  -> adds 10 to the manager's total_keys.

        total_keys/used_keys are read_only on ManagerProfileSerializer on
        purpose (a manager shouldn't be able to grant itself keys via a
        normal profile PATCH) - this is the one deliberate, owner-only door
        for adjusting that number.
        """
        manager = self.get_object()

        try:
            keys_to_add = int(request.data.get("keys"))
        except (TypeError, ValueError):
            return Response(
                {"detail": "keys must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if keys_to_add <= 0:
            return Response(
                {"detail": "keys must be a positive integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        manager.total_keys = (manager.total_keys or 0) + keys_to_add
        manager.save(update_fields=["total_keys"])

        AuditLog.objects.create(
            manager=manager,
            action=AuditLog.ACTION_ALLOCATE_KEYS,
            status=AuditLog.STATUS_SUCCESS,
            payload={"keys_added": keys_to_add, "new_total": manager.total_keys},
        )

        return Response(
            {
                "detail": f"{keys_to_add} keys allocated.",
                "manager_id": manager.id,
                "total_keys": manager.total_keys,
                "used_keys": manager.used_keys,
                "keys_remaining": manager.keys_remaining(),
            },
            status=status.HTTP_200_OK,
        )


class OwnerForceDeleteUserView(APIView):
    """
    /api/owner/users/<id>/force_delete/
    Owner can force unenroll/delete a user via FcmCommand(UNENROLL).
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def post(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        device = getattr(customer, "device", None)

        if not device:
            customer.is_active = False
            customer.save(update_fields=["is_active"])
            return Response({"detail": "Customer deactivated (no device)."}, status=status.HTTP_200_OK)

        device.dpc_status = Device.DPC_STATUS_UNENROLL_PENDING
        device.save(update_fields=["dpc_status"])

        log = AuditLog.objects.create(
            manager=customer.manager,
            customer=customer,
            device=device,
            action=AuditLog.ACTION_DELETE_USER,
            status=AuditLog.STATUS_PENDING,
            payload={"forced_by_owner": True},
        )

        reg, _ = DeviceRegistration.objects.update_or_create(
            imei_1=device.imei1,
            defaults={
                "imei_2": device.imei2 or "",
                "fcm_token": device.dpc_fcm_token or "",
                "manager_id": customer.manager.id if customer.manager else None,
                "device_id": str(device.id),
                "user": customer.manager.user if customer.manager else None,
            },
        )

        cmd = FcmCommand.objects.create(
            device=reg,
            action="UNENROLL",
            payload={
                "audit_log_id": log.id,
                "customer_id": customer.id,
                "device_id": device.id,
                "manager_id": customer.manager.id if customer.manager else None,
                "forced_by_owner": True,
            },
        )
        send_fcm_command_task.delay(cmd.id)

        title = "Force unenroll requested"
        body = f"Owner forced unenroll for {customer.name} (IMEI {device.imei1})."
        send_fcm_to_owner(title, body, data={"audit_log_id": log.id})

        return Response(
            {"detail": "Force unenroll queued.", "audit_log_id": log.id},
            status=status.HTTP_202_ACCEPTED,
        )


class OwnerDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = OwnerDevice
        fields = ["id", "fcm_token", "platform", "is_active"]


class OwnerRegisterDeviceView(APIView):
    """
    /api/owner/devices/register/
    Called by OwnerApp to register/update its FCM token.
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def post(self, request):
        fcm_token = request.data.get("fcm_token")
        platform = request.data.get("platform", "android")
        if not fcm_token:
            return Response({"detail": "fcm_token required"}, status=status.HTTP_400_BAD_REQUEST)

        device, created = OwnerDevice.objects.update_or_create(
            fcm_token=fcm_token,
            defaults={
                "user": request.user,
                "platform": platform,
                "is_active": True,
            },
        )
        ser = OwnerDeviceSerializer(device)
        return Response(ser.data, status=status.HTTP_200_OK)
class OwnerProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = request.user.owner_profile
        except OwnerProfile.DoesNotExist:
            return Response({"detail": "Owner profile not found"}, status=404)

        serializer = OwnerProfileSerializer(profile)
        return Response(serializer.data)