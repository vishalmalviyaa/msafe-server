from django.db import models
from django.conf import settings
from users.models import TimeStampedModel


class OwnerDevice(TimeStampedModel):
    """
    Each OwnerApp installation registers itself here with its FCM token.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owner_devices",
    )
    fcm_token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=50, blank=True)  # android/ios/web
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"OwnerDevice(user={self.user.username}, platform={self.platform})"
class OwnerProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owner_profile",
    )

    phone = models.CharField(max_length=20, blank=True)
    photo = models.ImageField(upload_to="owners/photos/", null=True, blank=True)

    def __str__(self):
        return f"OwnerProfile({self.user.username})"