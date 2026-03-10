import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import FcmCommand, CommandAck, AuditLog
from .utils import FcmError, send_fcm_data_message, utcnow

from users.models import Device as DomainDevice, AuditLog as DomainAuditLog
from users.utils import send_fcm_to_manager, send_fcm_to_owner

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def send_fcm_command_task(self, command_id: int) -> None:
    """
    Send a single FcmCommand via FCM with retry.

    States:
      - PENDING -> SENT (on success, waiting for ACK)
      - PENDING -> FAILED (on permanent error after retries)
    """
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
    """
    Periodic task: re-send stale SENT/PENDING commands that lack ACK.
    """
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
    """
    Reconcile CommandAck with FcmCommand and update your domain models:

      - LOCK   -> users.Device.lock_status + users.AuditLog
      - UNLOCK -> users.Device.lock_status + users.AuditLog
      - UNENROLL -> users.Device.dpc_status, Customer.is_active + users.AuditLog

    DPC sends ACK to /api/system/devices/ack/.
    """
    try:
        command = (
            FcmCommand.objects
            .select_related("device")
            .prefetch_related("acks")
            .get(pk=command_id)
        )
    except FcmCommand.DoesNotExist:
        return

    acks = list(command.acks.all())
    if not acks:
        return

    latest = acks[-1]
    status_str = latest.status.upper()
    success = status_str == "SUCCESS"

    reg = command.device

    try:
        device = DomainDevice.objects.select_related("customer__manager").get(imei1=reg.imei_1)
    except DomainDevice.DoesNotExist:
        # still mark command status
        command.status = "FAILED" if not success else "ACKED"
        command.save(update_fields=["status"])
        return

    customer = device.customer
    manager_profile = customer.manager

    payload = command.payload or {}
    audit_log_id = payload.get("audit_log_id")
    domain_log = None
    if audit_log_id:
        try:
            domain_log = DomainAuditLog.objects.get(id=audit_log_id)
        except DomainAuditLog.DoesNotExist:
            domain_log = None

    with transaction.atomic():
        # Update per action
        if command.action == "LOCK":
            device.lock_status = (
                DomainDevice.LOCK_STATUS_LOCKED if success else DomainDevice.LOCK_STATUS_UNLOCKED
            )
            device.save(update_fields=["lock_status"])

        elif command.action == "UNLOCK":
            device.lock_status = (
                DomainDevice.LOCK_STATUS_UNLOCKED if success else DomainDevice.LOCK_STATUS_LOCKED
            )
            device.save(update_fields=["lock_status"])

        elif command.action == "UNENROLL":
            if success:
                device.dpc_status = DomainDevice.DPC_STATUS_UNENROLLED
                device.lock_status = DomainDevice.LOCK_STATUS_UNLOCKED
                device.save(update_fields=["dpc_status", "lock_status"])
                customer.is_active = False
                customer.save(update_fields=["is_active"])
            else:
                device.dpc_status = DomainDevice.DPC_STATUS_ENROLLED
                device.save(update_fields=["dpc_status"])

        # Update domain AuditLog
        if domain_log:
            domain_log.status = (
                DomainAuditLog.STATUS_SUCCESS if success else DomainAuditLog.STATUS_FAILED
            )
            pl = domain_log.payload or {}
            pl["ack_payload"] = latest.raw_payload
            pl["ack_status"] = status_str
            pl["lock_status"] = device.lock_status
            domain_log.payload = pl
            domain_log.save(update_fields=["status", "payload"])

        # Update FcmCommand status
        command.status = "ACKED" if success else "FAILED"
        command.save(update_fields=["status"])

    # Notify manager/owner, similar to old /api/dpc/*_ack/ behavior
    title = ""
    body = ""
    if command.action == "LOCK":
        if success:
            title = "Device locked"
            body = f"User {customer.name} (IMEI {device.imei1}) is now locked."
        else:
            title = "Lock failed"
            body = f"Lock failed for {customer.name} (IMEI {device.imei1})."
    elif command.action == "UNLOCK":
        if success:
            title = "Device unlocked"
            body = f"User {customer.name} (IMEI {device.imei1}) is now unlocked."
        else:
            title = "Unlock failed"
            body = f"Unlock failed for {customer.name} (IMEI {device.imei1})."
    elif command.action == "UNENROLL":
        if success:
            title = "User unenrolled"
            body = f"User {customer.name} (IMEI {device.imei1}) unenrolled and DPC removed."
        else:
            title = "User unenroll failed"
            body = f"User {customer.name} (IMEI {device.imei1}) unenroll FAILED."

    if title:
        if manager_profile:
            send_fcm_to_manager(manager_profile, title, body, data={"audit_log_id": audit_log_id})
        send_fcm_to_owner(title, body, data={"audit_log_id": audit_log_id})
