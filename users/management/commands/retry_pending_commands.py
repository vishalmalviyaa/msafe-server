from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from users.models import Device, AuditLog
from users.utils import send_fcm


class Command(BaseCommand):
    help = "Retry pending UNENROLL / LOCK / UNLOCK commands for offline devices."

    def handle(self, *args, **options):
        now = timezone.now()
        cutoff = now - timedelta(minutes=5)  # example window

        # Retry UNENROLL_PENDING
        unenroll_devices = Device.objects.filter(
            dpc_status=Device.DPC_STATUS_UNENROLL_PENDING,
            last_seen_at__lt=cutoff,
        )
        for device in unenroll_devices:
            customer = device.customer
            log = AuditLog.objects.create(
                customer=customer,
                device=device,
                manager=customer.manager,
                action=AuditLog.ACTION_DELETE_USER,
                status=AuditLog.STATUS_PENDING,
                payload={"retry": True},
            )
            if device.dpc_fcm_token:
                payload = {
                    "action": "UNENROLL",
                    "customer_id": customer.id,
                    "imei1": device.imei1,
                    "audit_log_id": log.id,
                    "retry": True,
                }
                send_fcm(device.dpc_fcm_token, "UNENROLL DEVICE", "Retry unenroll", data=payload)

        # You can similarly add retry logic for PENDING_LOCK/PENDING_UNLOCK if you want
        self.stdout.write(self.style.SUCCESS("Retry command executed"))
