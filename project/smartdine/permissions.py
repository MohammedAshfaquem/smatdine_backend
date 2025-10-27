from rest_framework.permissions import BasePermission

class IsStaffRole(BasePermission):
    """
    Allow access only to authenticated users with a specific role (or roles).
    Set view.allowed_roles = ['admin','kitchen'] to restrict.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        allowed = getattr(view, "allowed_roles", None)
        if not allowed:
            # If allowed_roles not defined, default to any authenticated staff (excluding superusers)
            return request.user.is_active and not request.user.is_superuser
        return getattr(request.user, "role", None) in allowed or request.user.is_superuser




