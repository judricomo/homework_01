from rest_framework.permissions import BasePermission

from .models import Membership


class IsHouseholdAdministrator(BasePermission):
    message = "Household administrator permissions are required."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return Membership.objects.filter(
            user=request.user, role=Membership.Role.ADMIN, is_active=True
        ).exists()


class IsActiveHouseholdMember(BasePermission):
    message = "An active household membership is required."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and Membership.objects.filter(user=request.user, is_active=True).exists()
        )
