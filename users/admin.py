from django.contrib import admin
from .models import Customer, Device, EnrollmentToken, AuditLog

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "phone", "manager", "is_active")
    search_fields = ("name", "phone")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("id", "imei1", "customer", "lock_status", "dpc_status", "last_seen_at")
    search_fields = ("imei1", "imei2")


@admin.register(EnrollmentToken)
class EnrollmentTokenAdmin(admin.ModelAdmin):
    list_display = ("token", "manager", "customer", "status", "expires_at")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "action", "status", "manager", "customer", "device", "created_at")
    list_filter = ("action", "status")
