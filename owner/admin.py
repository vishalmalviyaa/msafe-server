from django.contrib import admin
from .models import OwnerDevice


@admin.register(OwnerDevice)
class OwnerDeviceAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "platform", "is_active", "created_at")
    search_fields = ("user__username", "fcm_token")
    list_filter = ("platform", "is_active")
