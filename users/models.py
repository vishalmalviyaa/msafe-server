from django.db import models
from django.utils import timezone

from scalability_core.models import DeviceRegistration


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# =========================================================
# CUSTOMER
# =========================================================

class Customer(TimeStampedModel):
    """
    Business user (borrower / end user).
    """

    manager = models.ForeignKey(
        "manager.ManagerProfile",
        on_delete=models.CASCADE,
        related_name="customers",
        db_index=True,
    )

    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    address = models.TextField(blank=True)

    # Loan / EMI info
    loan_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    emi_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    emi_start_date = models.DateField(null=True, blank=True)
    emi_end_date = models.DateField(null=True, blank=True)

    # Photo & signature stored as S3 URLs
    photo = models.URLField(null=True, blank=True)
    signature = models.URLField(null=True, blank=True)

    # soft delete / active flag
    is_active = models.BooleanField(default=True, db_index=True)

    def __str__(self):
        return f"{self.name} ({self.phone})"


# =========================================================
# DEVICE
# =========================================================

class Device(TimeStampedModel):

    LOCK_STATUS_LOCKED = "LOCKED"
    LOCK_STATUS_UNLOCKED = "UNLOCKED"
    LOCK_STATUS_PENDING_LOCK = "PENDING_LOCK"
    LOCK_STATUS_PENDING_UNLOCK = "PENDING_UNLOCK"

    LOCK_STATUS_CHOICES = (
        (LOCK_STATUS_LOCKED, "Locked"),
        (LOCK_STATUS_UNLOCKED, "Unlocked"),
        (LOCK_STATUS_PENDING_LOCK, "Pending Lock"),
        (LOCK_STATUS_PENDING_UNLOCK, "Pending Unlock"),
    )

    DPC_STATUS_ENROLLED = "ENROLLED"
    DPC_STATUS_UNENROLL_PENDING = "UNENROLL_PENDING"
    DPC_STATUS_UNENROLLED = "UNENROLLED"

    DPC_STATUS_CHOICES = (
        (DPC_STATUS_ENROLLED, "Enrolled"),
        (DPC_STATUS_UNENROLL_PENDING, "Unenroll Pending"),
        (DPC_STATUS_UNENROLLED, "Unenrolled"),
    )

    customer = models.OneToOneField(
        Customer,
        on_delete=models.CASCADE,
        related_name="device",
        db_index=True,
    )

    imei1 = models.CharField(max_length=32, unique=True, db_index=True)
    imei2 = models.CharField(max_length=32, unique=True, null=True, blank=True, db_index=True)

    mobile_name = models.CharField(max_length=255, blank=True)
    mobile_number = models.CharField(max_length=20, blank=True)

    # SIMs
    sim1_number = models.CharField(max_length=20, blank=True)
    sim2_number = models.CharField(max_length=20, blank=True)

    # Location (only last known)
    last_location_lat = models.FloatField(null=True, blank=True)
    last_location_lng = models.FloatField(null=True, blank=True)
    last_location_time = models.DateTimeField(null=True, blank=True)

    # Status
    lock_status = models.CharField(
        max_length=20,
        choices=LOCK_STATUS_CHOICES,
        default=LOCK_STATUS_UNLOCKED,
        db_index=True,
    )

    dpc_status = models.CharField(
        max_length=20,
        choices=DPC_STATUS_CHOICES,
        default=DPC_STATUS_ENROLLED,
        db_index=True,
    )

    last_seen_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # DPC FCM token (for push commands)
    dpc_fcm_token = models.CharField(max_length=255, null=True, blank=True)

    # Link into scalability_core infrastructure
    device_registration = models.OneToOneField(
        DeviceRegistration,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="legacy_device",
    )

    def __str__(self):
        return f"Device(IMEI1={self.imei1}, customer={self.customer})"

    class Meta:
        indexes = [
            models.Index(fields=["imei1"]),
            models.Index(fields=["imei2"]),
            models.Index(fields=["customer"]),
            models.Index(fields=["last_seen_at"]),
            models.Index(fields=["dpc_status"]),
            models.Index(fields=["lock_status"]),
        ]


# =========================================================
# ENROLLMENT TOKEN
# =========================================================

class EnrollmentToken(TimeStampedModel):

    STATUS_ACTIVE = "ACTIVE"
    STATUS_USED = "USED"
    STATUS_EXPIRED = "EXPIRED"

    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Active"),
        (STATUS_USED, "Used"),
        (STATUS_EXPIRED, "Expired"),
    )

    token = models.CharField(max_length=128, unique=True, db_index=True)

    manager = models.ForeignKey(
        "manager.ManagerProfile",
        on_delete=models.CASCADE,
        related_name="enrollment_tokens",
        db_index=True,
    )

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="enrollment_tokens",
        db_index=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
    )

    expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"EnrollmentToken({self.token}, {self.status})"


# =========================================================
# AUDIT LOG
# =========================================================

class AuditLog(TimeStampedModel):

    ACTION_DELETE_USER = "DELETE_USER"
    ACTION_ENROLL_USER = "ENROLL_USER"
    ACTION_LOCK_USER = "LOCK_USER"
    ACTION_UNLOCK_USER = "UNLOCK_USER"
    ACTION_UPDATE_LOCATION = "UPDATE_LOCATION"
    ACTION_SIM_CHANGE = "SIM_CHANGE"

    ACTION_CHOICES = (
        (ACTION_DELETE_USER, "Delete User"),
        (ACTION_ENROLL_USER, "Enroll User"),
        (ACTION_LOCK_USER, "Lock User"),
        (ACTION_UNLOCK_USER, "Unlock User"),
        (ACTION_UPDATE_LOCATION, "Update Location"),
        (ACTION_SIM_CHANGE, "SIM Change"),
    )

    STATUS_SUCCESS = "SUCCESS"
    STATUS_FAILED = "FAILED"
    STATUS_PENDING = "PENDING"

    STATUS_CHOICES = (
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
        (STATUS_PENDING, "Pending"),
    )

    manager = models.ForeignKey(
        "manager.ManagerProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        db_index=True,
    )

    customer = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        db_index=True,
    )

    device = models.ForeignKey(
        Device,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        db_index=True,
    )

    action = models.CharField(max_length=50, choices=ACTION_CHOICES, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)

    payload = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"AuditLog({self.action}, {self.status}, id={self.id})"

    class Meta:
        indexes = [
            models.Index(fields=["manager"]),
            models.Index(fields=["customer"]),
            models.Index(fields=["device"]),
            models.Index(fields=["action"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]