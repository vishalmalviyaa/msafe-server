from rest_framework.permissions import BasePermission, SAFE_METHODS


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
