from rest_framework.permissions import BasePermission

class IsStaffRole(BasePermission):

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        allowed = getattr(view, "allowed_roles", None)
        if not allowed:
            return request.user.is_active and not request.user.is_superuser
        return getattr(request.user, "role", None) in allowed or request.user.is_superuser




