from django.db import transaction
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone

from .models import Chore, ChoreAssignment, Membership
from .permissions import IsActiveHouseholdMember, IsHouseholdAdministrator
from .serializers import (
    AddMembershipSerializer,
    MembershipRoleSerializer,
    MembershipSerializer,
    ChoreSerializer,
    ChoreWorkSerializer,
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


class ChoreViewSet(viewsets.ModelViewSet):
    serializer_class = ChoreSerializer
    permission_classes = (IsHouseholdAdministrator,)
    pagination_class = type("ChorePagination", (PageNumberPagination,), {"page_size": 50})

    def get_household(self):
        return Membership.objects.get(
            user=self.request.user, role=Membership.Role.ADMIN, is_active=True
        ).household

    def get_queryset(self):
        return Chore.objects.filter(household=self.get_household()).order_by("id")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["household"] = self.get_household()
        return context

    def perform_create(self, serializer):
        serializer.save(household=self.get_household())


class ChoreQueueViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (IsActiveHouseholdMember,)
    serializer_class = ChoreWorkSerializer
    pagination_class = type("ChorePagination", (PageNumberPagination,), {"page_size": 50})

    def get_membership(self):
        return Membership.objects.get(user=self.request.user, is_active=True)

    def get_queryset(self):
        membership = self.get_membership()
        assigned = Chore.objects.filter(
            household_id=membership.household_id,
            assignments__membership=membership,
            assignments__is_active=True,
        )
        claimable = Chore.objects.filter(
            household_id=membership.household_id,
            assignment_mode=Chore.AssignmentMode.CLAIM,
            anchor_date__lte=timezone.localdate(),
        ).exclude(assignments__is_active=True)
        return (assigned | claimable).distinct().order_by("id")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["membership"] = self.get_membership()
        return context

    @action(detail=True, methods=["post"])
    def claim(self, request, pk=None):
        membership = self.get_membership()
        chore = get_object_or_404(
            Chore.objects.filter(
                household_id=membership.household_id,
                assignment_mode=Chore.AssignmentMode.CLAIM,
            ),
            pk=pk,
        )
        if chore.next_due_date() > timezone.localdate():
            return Response(
                {"detail": "This claim-pool chore is not currently available."},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            ChoreAssignment.claim(chore, membership)
        except (ValidationError, DjangoValidationError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(
            ChoreWorkSerializer(
                chore, context=self.get_serializer_context()
            ).data,
            status=status.HTTP_201_CREATED,
        )
