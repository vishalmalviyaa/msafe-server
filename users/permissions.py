from rest_framework.permissions import BasePermission
from django.conf import settings


class IsManagerOfCustomer(BasePermission):
    """
    Object-level check: only the manager who owns this customer/device can act.
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user.is_authenticated or not hasattr(user, "manager_profile"):
            return False

        manager_profile = user.manager_profile

        # obj can be Customer or Device
        if hasattr(obj, "manager"):
            return obj.manager == manager_profile
        if hasattr(obj, "customer"):
            return obj.customer.manager == manager_profile
        return False


class IsDPCClient(BasePermission):
    """
    DPC endpoints must include correct API key header:
    X-DPC-API-KEY: <settings.DPC_API_KEY>
    """

    def has_permission(self, request, view):
        expected = getattr(settings, "DPC_API_KEY", None)
        if not expected:
            return False
        provided = request.headers.get("X-DPC-API-KEY")
        return provided == expected
