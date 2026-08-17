from rest_framework.permissions import BasePermission


class IsOwner(BasePermission):
    """
    Allows authenticated Owner accounts.

    An Owner is either:
    - Django superuser, OR
    - Django staff user.

    This matches the logic used by /api/auth/me/.
    """

    message = "Owner permission required."

    def has_permission(self, request, view):
        user = request.user

        return (
            bool(user)
            and user.is_authenticated
            and (user.is_superuser or user.is_staff)
        )