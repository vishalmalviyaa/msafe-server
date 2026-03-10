from django.conf import settings
from django.db import models


class DeviceRegistration(models.Model):
    """Maps a Django user to one or more physical devices + FCM tokens."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="device_registrations",
    )
    # Optional: manager / owner relationships can be wired via your domain models
    manager_id = models.IntegerField(null=True, blank=True)
    imei_1 = models.CharField(max_length=32, db_index=True)
    imei_2 = models.CharField(max_length=32, null=True, blank=True)
    device_id = models.CharField(max_length=128, db_index=True)
    fcm_token = models.CharField(max_length=512, db_index=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    last_ip = models.GenericIPAddressField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["manager_id"]),
            models.Index(fields=["imei_1"]),
            models.Index(fields=["device_id"]),
            models.Index(fields=["fcm_token"]),
        ]

    def __str__(self) -> str:
        return f"DeviceRegistration(user={self.user_id}, imei={self.imei_1})"


class FcmCommand(models.Model):
    """Outbound command sent to a device via FCM (LOCK, UNENROLL, etc.)."""

    ACTION_CHOICES = [
        ("LOCK", "LOCK"),
        ("UNLOCK", "UNLOCK"),
        ("UNENROLL", "UNENROLL"),
        ("MESSAGE", "MESSAGE"),
        ("OTHER", "OTHER"),
    ]

    STATUS_CHOICES = [
        ("PENDING", "PENDING"),  # created, not yet attempted
        ("SENT", "SENT"),        # sent to FCM
        ("ACKED", "ACKED"),      # device acknowledged
        ("FAILED", "FAILED"),    # permanent failure
    ]

    device = models.ForeignKey(
        DeviceRegistration,
        on_delete=models.CASCADE,
        related_name="commands",
    )
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default="PENDING"
    )
    fcm_message_id = models.CharField(
        max_length=128, null=True, blank=True, db_index=True
    )
    retry_count = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["action"]),
        ]

    def __str__(self) -> str:
        return f"FcmCommand(device={self.device_id}, action={self.action}, status={self.status})"


class CommandAck(models.Model):
    """Raw ACK from a device for a given FcmCommand."""

    command = models.ForeignKey(
        FcmCommand,
        on_delete=models.CASCADE,
        related_name="acks",
    )
    status = models.CharField(max_length=32)  # SUCCESS / FAILED / OTHER
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"CommandAck(command={self.command_id}, status={self.status})"


class AuditLog(models.Model):
    """Immutable audit trail for sensitive actions.

    Examples:
      - DELETE_USER
      - ENROLL_DEVICE
      - UNENROLL_DEVICE
      - LOCK_DEVICE
      - UNLOCK_DEVICE
    """

    ACTOR_TYPE_CHOICES = [
        ("owner", "Owner"),
        ("manager", "Manager"),
        ("system", "System"),
    ]

    STATUS_CHOICES = [
        ("PENDING", "PENDING"),
        ("SUCCESS", "SUCCESS"),
        ("FAILED", "FAILED"),
    ]

    actor_type = models.CharField(max_length=16, choices=ACTOR_TYPE_CHOICES)
    actor_id = models.IntegerField(null=True, blank=True)
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    device = models.ForeignKey(
        DeviceRegistration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=64)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default="PENDING"
    )
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["actor_type", "actor_id"]),
            models.Index(fields=["action"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"AuditLog(action={self.action}, status={self.status})"


class LocationPing(models.Model):
    """Stores live location & SIM metadata snapshots from devices (time-series)."""

    device = models.ForeignKey(
        DeviceRegistration,
        on_delete=models.CASCADE,
        related_name="location_pings",
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    accuracy_m = models.FloatField(null=True, blank=True)
    sim_numbers = models.JSONField(default=list, blank=True)
    captured_at = models.DateTimeField()  # device local timestamp
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["device", "captured_at"]),
            models.Index(fields=["received_at"]),
        ]

    def __str__(self) -> str:
        return f"LocationPing(device={self.device_id}, lat={self.latitude}, lon={self.longitude})"
