from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import Device, AuditLog
from .utils import send_fcm


class SendDeviceCommandView(APIView):
    """
    POST /api/device/command/

    BODY:
    {
        "imei1": "123456789012345",
        "command": "PLAY_SOUND"
    }
    """

    permission_classes = [IsAuthenticated]

    ALLOWED_COMMANDS = [
        "PLAY_SOUND",
        "FORCE_LOCATION",
        "REBOOT_DEVICE",
    ]

    def post(self, request):

        imei1 = request.data.get("imei1")
        command = request.data.get("command")

        if not imei1 or not command:
            return Response(
                {"detail": "imei1 and command required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if command not in self.ALLOWED_COMMANDS:
            return Response(
                {"detail": "Invalid command"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        device = get_object_or_404(Device, imei1=imei1)

        manager = request.user.manager_profile

        log = AuditLog.objects.create(
            manager=manager,
            customer=device.customer,
            device=device,
            action=command,
            status=AuditLog.STATUS_PENDING,
            payload={}
        )

        if device.dpc_fcm_token:
            send_fcm(
                device.dpc_fcm_token,
                "Device Command",
                command,
                data={
                    "action": command,
                    "imei1": device.imei1,
                    "audit_log_id": log.id,
                },
            )

        return Response(
            {
                "detail": "Command sent",
                "audit_log_id": log.id
            }
        )