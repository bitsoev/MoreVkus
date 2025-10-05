from rest_framework.permissions import BasePermission


class IsOwnerOrAdmin(BasePermission):
    """Разрешает доступ владельцу объекта или администратору"""
    def has_object_permission(self, request, view, obj):
        return getattr(obj, "user", None) == request.user or request.user.is_staff
