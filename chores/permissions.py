from rest_framework.permissions import BasePermission

from .models import Membership


class IsHouseholdAdministrator(BasePermission):
    message = "Household administrator permissions are required."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return Membership.objects.filter(
            user=request.user, role=Membership.Role.ADMIN
        ).exists()
