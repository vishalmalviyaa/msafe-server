from __future__ import annotations

from typing import Optional

from celery import shared_task
from django.utils import timezone

from .models import AuditLog
from .utils import send_fcm


def _get_log_with_relations(audit_log_id: int) -> Optional[AuditLog]:
    try:
        return AuditLog.objects.select_related("customer", "device", "manager").get(pk=audit_log_id)
    except AuditLog.DoesNotExist:
        return None


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def send_lock_command_task(self, audit_log_id: int) -> None:
    """
    Retryable FCM sender for LOCK.
    """
    log = _get_log_with_relations(audit_log_id)
    if not log:
        return

    customer = log.customer
    device = log.device

    if not device or not device.dpc_fcm_token:
        log.status = AuditLog.STATUS_FAILED
        payload = log.payload or {}
        payload["error"] = "No active device or missing FCM token"
        log.payload = payload
        log.save(update_fields=["status", "payload"])
        return

    payload = log.payload or {}
    lock_message = payload.get("message", "Device locked")
    logo_url = payload.get("logo_url", "")

    fcm_data = {
        "action": "LOCK",
        "message": lock_message,
        "logo_url": logo_url,
        "customer_id": customer.id if customer else None,
        "imei1": device.imei1,
        "audit_log_id": log.id,
    }

    try:
        send_fcm(
            device.dpc_fcm_token,
            "LOCK DEVICE",
            lock_message,
            data=fcm_data,
        )
        payload["send_status"] = "SENT"
        payload["last_send_at"] = timezone.now().isoformat()
        log.payload = payload
        log.save(update_fields=["payload"])
    except Exception as exc:
        payload["send_status"] = "FAILED_RETRYING"
        payload["last_error"] = str(exc)
        log.payload = payload
        log.save(update_fields=["payload"])
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def send_unlock_command_task(self, audit_log_id: int) -> None:
    """
    Retryable FCM sender for UNLOCK.
    """
    log = _get_log_with_relations(audit_log_id)
    if not log:
        return

    customer = log.customer
    device = log.device

    if not device or not device.dpc_fcm_token:
        log.status = AuditLog.STATUS_FAILED
        payload = log.payload or {}
        payload["error"] = "No active device or missing FCM token"
        log.payload = payload
        log.save(update_fields=["status", "payload"])
        return

    fcm_data = {
        "action": "UNLOCK",
        "customer_id": customer.id if customer else None,
        "imei1": device.imei1,
        "audit_log_id": log.id,
    }

    try:
        send_fcm(
            device.dpc_fcm_token,
            "UNLOCK DEVICE",
            "Unlock device",
            data=fcm_data,
        )
        payload = log.payload or {}
        payload["send_status"] = "SENT"
        payload["last_send_at"] = timezone.now().isoformat()
        log.payload = payload
        log.save(update_fields=["payload"])
    except Exception as exc:
        payload = log.payload or {}
        payload["send_status"] = "FAILED_RETRYING"
        payload["last_error"] = str(exc)
        log.payload = payload
        log.save(update_fields=["payload"])
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def send_unenroll_command_task(self, audit_log_id: int) -> None:
    """
    Retryable FCM sender for UNENROLL (used by manager + owner).
    """
    log = _get_log_with_relations(audit_log_id)
    if not log:
        return

    customer = log.customer
    device = log.device

    if not device or not device.dpc_fcm_token:
        log.status = AuditLog.STATUS_FAILED
        payload = log.payload or {}
        payload["error"] = "No active device or missing FCM token"
        log.payload = payload
        log.save(update_fields=["status", "payload"])
        return

    payload = log.payload or {}
    forced_by_owner = payload.get("forced_by_owner", False)

    fcm_data = {
        "action": "UNENROLL",
        "customer_id": customer.id if customer else None,
        "imei1": device.imei1,
        "audit_log_id": log.id,
        "forced_by_owner": forced_by_owner,
    }

    title = "UNENROLL DEVICE"
    body = "Remove control (by owner)" if forced_by_owner else "Remove control"

    try:
        send_fcm(
            device.dpc_fcm_token,
            title,
            body,
            data=fcm_data,
        )
        payload["send_status"] = "SENT"
        payload["last_send_at"] = timezone.now().isoformat()
        log.payload = payload
        log.save(update_fields=["payload"])
    except Exception as exc:
        payload["send_status"] = "FAILED_RETRYING"
        payload["last_error"] = str(exc)
        log.payload = payload
        log.save(update_fields=["status", "payload"])
        raise self.retry(exc=exc)
