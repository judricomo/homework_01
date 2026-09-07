from django.db import transaction
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.conf import settings
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import Chore, ChoreAssignment, Completion, Membership, PointsLedger
from .permissions import IsActiveHouseholdMember, IsHouseholdAdministrator
from .services import calculate_next_due_date
from .serializers import (
    AddMembershipSerializer,
    MembershipRoleSerializer,
    MembershipSerializer,
    ChoreSerializer,
    ChoreWorkSerializer,
    CompletionSerializer, CompletionSubmissionSerializer, CompletionReviewSerializer,
    LeaderboardSerializer, DueSurfaceSerializer,
)

FILTER_VALUES = {
    "assignment_mode": set(Chore.AssignmentMode.values),
    "recurrence_mode": set(Chore.RecurrenceMode.values),
    "due_state": {"upcoming", "due", "overdue"},
}


class ChoreFilterMixin:
    """Apply the public, bounded chore-list filters without widening visibility."""

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        for field, allowed in FILTER_VALUES.items():
            values = self.request.query_params.getlist(field)
            if not values:
                continue
            unique_values = set(values)
            if len(unique_values) != 1 or next(iter(unique_values), None) not in allowed:
                raise ValidationError(
                    {field: f"Use one of: {', '.join(sorted(allowed))}."}
                )
            value = values[0]
            if field != "due_state":
                queryset = queryset.filter(**{field: value})
            else:
                queryset = [
                    chore for chore in queryset
                    if ChoreWorkSerializer.due_state_for(chore) == value
                ]
        return queryset


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


class ChoreViewSet(ChoreFilterMixin, viewsets.ModelViewSet):
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


class ChoreQueueViewSet(ChoreFilterMixin, viewsets.ReadOnlyModelViewSet):
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

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        membership = self.get_membership()
        chore = get_object_or_404(
            Chore.objects.filter(household_id=membership.household_id), pk=pk
        )
        serializer = CompletionSubmissionSerializer(
            data=request.data, context={"membership": membership}
        )
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("chore", chore).pk != chore.pk:
            raise ValidationError({"chore": "Chore does not match the route."})
        try:
            completion = Completion.submit(
                membership=membership, chore=chore,
                occurrence=serializer.validated_data["occurrence"],
            )
        except DjangoValidationError as exc:
            raise ValidationError({"detail": exc.messages}) from exc
        return Response(CompletionSerializer(completion).data, status=status.HTTP_201_CREATED)


class CompletionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (IsActiveHouseholdMember,)
    serializer_class = CompletionSerializer

    def get_membership(self):
        return Membership.objects.get(user=self.request.user, is_active=True)

    def get_queryset(self):
        membership = self.get_membership()
        return Completion.objects.filter(
            household_id=membership.household_id
        ).select_related("chore", "assignment", "submitted_by__user", "reviewer__user")

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        membership = self.get_membership()
        completion = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = CompletionReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            completion = Completion.review(
                completion_id=completion.pk, reviewer=membership,
                status=serializer.validated_data["status"],
            )
        except DjangoValidationError as exc:
            raise ValidationError({"detail": exc.messages}) from exc
        return Response(CompletionSerializer(completion).data)


class LeaderboardView(generics.GenericAPIView):
    permission_classes = (IsActiveHouseholdMember,)
    serializer_class = LeaderboardSerializer

    def get_membership(self):
        return Membership.objects.select_related("household").get(
            user=self.request.user, is_active=True
        )

    def get(self, request, *args, **kwargs):
        membership = self.get_membership()
        reference_time = timezone.now()
        period_start = period_end = None
        view_name = self.kwargs.get("period", "all_time")
        if view_name == "current_period":
            local_reference = timezone.localtime(reference_time)
            start_date = local_reference.date() - timedelta(days=local_reference.weekday())
            period_start = timezone.make_aware(
                datetime.combine(start_date, time.min),
                timezone.get_current_timezone(),
            )
            period_end = timezone.make_aware(
                datetime.combine(start_date + timedelta(days=7), time.min),
                timezone.get_current_timezone(),
            )

        award_filter = (
            Q(
                points_ledger_entries__awarded_at__gte=period_start,
                points_ledger_entries__awarded_at__lt=period_end,
                points_ledger_entries__completion__status=Completion.Status.APPROVED,
            )
            if period_start is not None
            else Q(points_ledger_entries__completion__status=Completion.Status.APPROVED)
        )
        members = list(
            Membership.objects.filter(
                household_id=membership.household_id, is_active=True
            ).select_related("user").annotate(
                score_total=Coalesce(
                    Sum(
                        "points_ledger_entries__points",
                        filter=award_filter,
                    ),
                    0,
                )
            ).order_by("-score_total", "id")
        )
        rows = []
        previous_total = None
        rank = 0
        for index, member in enumerate(members, start=1):
            if member.score_total != previous_total:
                rank = index
                previous_total = member.score_total
            rows.append({
                "member_id": member.id,
                "username": member.user.username,
                "total_points": member.score_total,
                "rank": rank,
            })
        payload = {
            "view": view_name,
            "timezone": settings.TIME_ZONE,
            "members": rows,
        }
        if period_start is not None:
            payload.update({
                "period_type": "calendar_week",
                "period_start": period_start,
                "period_end": period_end,
                "reference_time": reference_time,
            })
        return Response(self.get_serializer(payload).data)


class DueSurfaceView(generics.GenericAPIView):
    """Read-only, household-scoped due and overdue work for the current member."""

    permission_classes = (IsActiveHouseholdMember,)
    serializer_class = DueSurfaceSerializer

    def get_membership(self):
        return Membership.objects.select_related("household", "user").get(
            user=self.request.user, is_active=True
        )

    def get(self, request, *args, **kwargs):
        membership = self.get_membership()
        project_zone = ZoneInfo(settings.TIME_ZONE)
        as_of = timezone.now()
        local_today = timezone.localtime(as_of, project_zone).date()
        chores = Chore.objects.filter(
            household_id=membership.household_id,
        ).prefetch_related("assignments__membership__user", "completions")

        items = []
        for chore in chores.order_by("id"):
            approved = [
                completion for completion in chore.completions.all()
                if completion.status == Completion.Status.APPROVED
            ]
            due_date = calculate_next_due_date(chore, completions=approved)
            if due_date > local_today:
                continue

            assignment = next(
                (
                    candidate for candidate in chore.assignments.all()
                    if candidate.is_active
                    and candidate.membership_id == membership.id
                    and candidate.membership.is_active
                ),
                None,
            )
            claimable = (
                chore.assignment_mode == Chore.AssignmentMode.CLAIM
                and not any(candidate.is_active for candidate in chore.assignments.all())
            )
            if assignment is None and not claimable:
                continue

            # An approved occurrence is complete even if stale assignment data
            # remains; pending and rejected records intentionally remain visible.
            if assignment and any(
                completion.occurrence == assignment.occurrence
                and completion.status == Completion.Status.APPROVED
                for completion in chore.completions.all()
            ):
                continue

            due_at = timezone.make_aware(datetime.combine(due_date, time.min), project_zone)
            due_state = "due" if local_today == due_date else "overdue"
            items.append({
                "chore": {"id": chore.id, "name": chore.name},
                "occurrence": assignment.occurrence if assignment else None,
                "assignment": (
                    {
                        "membership_id": assignment.membership_id,
                        "username": assignment.membership.user.username,
                    }
                    if assignment else None
                ),
                "claimable": claimable,
                "due_date": due_date,
                "due_at": due_at,
                "due_state": due_state,
                "recurrence": ChoreSerializer(chore).data["recurrence"],
            })

        payload = {
            "timezone": settings.TIME_ZONE,
            "as_of": as_of,
            "due": [item for item in items if item["due_state"] == "due"],
            "overdue": [item for item in items if item["due_state"] == "overdue"],
        }
        return Response(self.get_serializer(payload).data)
