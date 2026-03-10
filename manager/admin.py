from django.contrib import admin
from .models import ManagerProfile

@admin.register(ManagerProfile)
class ManagerProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "phone", "total_keys", "used_keys")
