from django.conf import settings
from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsDeviceBootstrapClient(BasePermission):
    """
    First-contact registration only: a brand-new device doesn't have a
    per-device token yet, so it proves itself with a shared bootstrap
    secret baked into the agent app (X-DEVICE-BOOTSTRAP-KEY header).

    Once registered, all further calls (heartbeat, location, ack) must use
    IsValidDeviceToken instead - the bootstrap key is intentionally never
    enough on its own to act as an already-registered device.
    """

    def has_permission(self, request, view):
        expected = getattr(settings, "DEVICE_BOOTSTRAP_KEY", None)
        if not expected:
            return False
        provided = request.headers.get("X-DEVICE-BOOTSTRAP-KEY")
        return provided == expected


class IsValidDeviceToken(BasePermission):
    """
    Requires the caller to present the device_id + the device_token that
    was issued to that specific device at registration time
    (X-DEVICE-TOKEN header). Without this, anyone who can guess a
    device_id/command_id can spoof heartbeats, locations, or command acks
    for a device they don't control.

    On success, the matching DeviceRegistration is attached to the request
    as `request.device` so views don't need to look it up (or trust a
    client-supplied FK id) again.
    """

    def has_permission(self, request, view):
        from .models import DeviceRegistration

        device_id = request.data.get("device_id") or request.query_params.get("device_id")
        token = request.headers.get("X-DEVICE-TOKEN")

        if not device_id or not token:
            return False

        device = DeviceRegistration.objects.filter(
            device_id=device_id, device_token=token
        ).first()

        if not device:
            return False

        request.device = device
        return True


class IsOwnerOrManager(BasePermission):
    """Simple RBAC via Django groups.

    - Users in group "owner" are treated as Owners.
    - Users in group "manager" are treated as Managers.
    Adjust to match your real roles if needed.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if request.method in SAFE_METHODS:
            return True
        groups = set(user.groups.values_list("name", flat=True))
        if "owner" in groups or "manager" in groups:
            return True
        return False
