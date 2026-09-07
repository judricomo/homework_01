from django.db import transaction
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Membership
from .permissions import IsHouseholdAdministrator
from .serializers import (
    AddMembershipSerializer,
    MembershipRoleSerializer,
    MembershipSerializer,
)


class HouseholdMembershipMixin:
    permission_classes = (IsHouseholdAdministrator,)

    def get_household(self):
        return Membership.objects.get(
            user=self.request.user, role=Membership.Role.ADMIN
        ).household

    def get_queryset(self):
        return Membership.objects.filter(
            household=self.get_household()
        ).select_related("user", "household")


class MembershipListCreateView(HouseholdMembershipMixin, generics.ListCreateAPIView):
    serializer_class = MembershipSerializer

    def get_serializer_class(self):
        return (
            AddMembershipSerializer
            if self.request.method == "POST"
            else MembershipSerializer
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["household"] = self.get_household()
        return context

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = serializer.save()
        return Response(
            MembershipSerializer(
                membership, context=self.get_serializer_context()
            ).data,
            status=status.HTTP_201_CREATED,
        )


class MembershipDetailView(
    HouseholdMembershipMixin, generics.RetrieveUpdateDestroyAPIView
):
    serializer_class = MembershipSerializer
    http_method_names = ("get", "patch", "put", "delete", "head", "options")

    def get_serializer_class(self):
        return (
            MembershipRoleSerializer
            if self.request.method in ("PATCH", "PUT")
            else MembershipSerializer
        )

    @transaction.atomic
    def perform_update(self, serializer):
        membership = Membership.objects.select_for_update().get(
            pk=self.get_object().pk
        )
        new_role = serializer.validated_data["role"]
        if (
            membership.role == Membership.Role.ADMIN
            and new_role == Membership.Role.MEMBER
            and Membership.objects.filter(
                household=membership.household, role=Membership.Role.ADMIN
            ).count()
            <= 1
        ):
            raise ValidationError(
                {"role": "The household must retain at least one administrator."}
            )
        serializer.instance = membership
        serializer.save()

    @transaction.atomic
    def perform_destroy(self, instance):
        membership = Membership.objects.select_for_update().get(pk=instance.pk)
        if (
            membership.role == Membership.Role.ADMIN
            and Membership.objects.filter(
                household=membership.household, role=Membership.Role.ADMIN
            ).count()
            <= 1
        ):
            raise ValidationError(
                {"detail": "The household must retain at least one administrator."}
            )
        instance.delete()
