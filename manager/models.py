from django.db import models
from django.conf import settings
from users.models import TimeStampedModel


class ManagerProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="manager_profile",
    )

    phone = models.CharField(max_length=20, blank=True)
    photo = models.ImageField(upload_to="managers/photos/", null=True, blank=True)

    # Default lock settings
    default_lock_message = models.TextField(blank=True, default="")
    default_lock_logo = models.ImageField(upload_to="managers/lock_logos/", null=True, blank=True)

    # Keys (enrollment)
    total_keys = models.PositiveIntegerField(default=0)
    used_keys = models.PositiveIntegerField(default=0)

    # Manager app FCM
    fcm_token = models.CharField(max_length=255, null=True, blank=True)

    def keys_remaining(self):
        return self.total_keys - self.used_keys

    @property
    def default_lock_logo_url(self):
        """
        Safely return public URL for default lock logo (if any),
        otherwise empty string.
        """
        try:
            if self.default_lock_logo and hasattr(self.default_lock_logo, "url"):
                return self.default_lock_logo.url
        except Exception:
            pass
        return ""

    def __str__(self):
        return f"ManagerProfile({self.user.username})"
