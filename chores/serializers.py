from django.contrib.auth import get_user_model
from rest_framework import serializers
from django.utils import timezone

from .models import Membership
from .models import Chore, ChoreAssignment, Completion


class MembershipSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    household = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = ("id", "user", "household", "role", "created_at", "updated_at")
        read_only_fields = fields

    def get_user(self, membership):
        user = membership.user
        return {"id": user.id, "username": user.username, "email": user.email}

    def get_household(self, membership):
        household = membership.household
        return {"id": household.id, "name": household.name}


class AddMembershipSerializer(serializers.Serializer):
    email = serializers.CharField()

    def validate_email(self, value):
        email = value.strip()
        if not email:
            raise serializers.ValidationError("Email is required.")
        return email

    def validate(self, attrs):
        user_model = get_user_model()
        users = user_model.objects.filter(email__iexact=attrs["email"])
        count = users.count()
        if count == 0:
            raise serializers.ValidationError(
                {"email": "No existing user was found with this email."}
            )
        if count > 1:
            raise serializers.ValidationError(
                {"email": "More than one existing user matches this email."}
            )
        user = users.first()
        household = self.context["household"]
        if Membership.objects.filter(user=user).exists():
            raise serializers.ValidationError(
                {"email": "This user already belongs to a household."}
            )
        attrs["user"] = user
        attrs["household"] = household
        return attrs

    def create(self, validated_data):
        return Membership.objects.create(
            household=validated_data["household"],
            user=validated_data["user"],
            role=Membership.Role.MEMBER,
        )


class MembershipRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membership
        fields = ("role",)

    def validate_role(self, value):
        if value not in (Membership.Role.ADMIN, Membership.Role.MEMBER):
            raise serializers.ValidationError("Role must be admin or member.")
        return value


class ChoreSerializer(serializers.ModelSerializer):
    points = serializers.IntegerField(read_only=True)
    recurrence = serializers.SerializerMethodField()
    due_date = serializers.SerializerMethodField()

    class Meta:
        model = Chore
        fields = (
            "id", "name", "difficulty", "points", "assignment_mode",
            "recurrence_mode", "fixed_recurrence", "recurrence_interval_days",
            "selected_weekdays", "anchor_date", "recurrence", "due_date",
        )
        read_only_fields = ("id", "points", "recurrence", "due_date")

    def validate(self, attrs):
        instance = self.instance or Chore(
            household=self.context["household"], **attrs
        )
        for key, value in attrs.items():
            setattr(instance, key, value)
        instance.full_clean(validate_constraints=False)
        return attrs

    def get_recurrence(self, obj):
        if obj.recurrence_mode == Chore.RecurrenceMode.FLEXIBLE:
            return {"mode": "flexible", "interval_days": obj.recurrence_interval_days}
        return {
            "mode": "fixed",
            "rule": obj.fixed_recurrence,
            "interval_days": obj.recurrence_interval_days,
            "weekdays": obj.selected_weekdays,
        }

    def get_due_date(self, obj):
        return obj.next_due_date().isoformat()


class ChoreWorkSerializer(ChoreSerializer):
    assignee = serializers.SerializerMethodField()
    claimable = serializers.SerializerMethodField()
    due_state = serializers.SerializerMethodField()
    occurrence = serializers.SerializerMethodField()

    class Meta(ChoreSerializer.Meta):
        fields = ChoreSerializer.Meta.fields + (
            "assignee", "claimable", "due_state", "occurrence",
        )

    def _assignment(self, obj):
        membership = self.context["membership"]
        return obj.assignments.filter(
            is_active=True, membership__household_id=membership.household_id
        ).first()

    def get_assignee(self, obj):
        assignment = self._assignment(obj)
        if not assignment:
            return None
        return {
            "membership_id": assignment.membership_id,
            "username": assignment.membership.user.username,
        }

    def get_claimable(self, obj):
        return obj.assignment_mode == Chore.AssignmentMode.CLAIM and not self._assignment(obj)

    def get_due_state(self, obj):
        return self.due_state_for(obj)

    def get_occurrence(self, obj):
        assignment = self._assignment(obj)
        return str(assignment.occurrence) if assignment else None

    @staticmethod
    def due_state_for(chore):
        due = chore.next_due_date()
        today = timezone.localdate()
        if today > due:
            return "overdue"
        if today == due:
            return "due"
        return "upcoming"


class CompletionSerializer(serializers.ModelSerializer):
    submitter = serializers.SerializerMethodField()
    reviewer_detail = serializers.SerializerMethodField()

    class Meta:
        model = Completion
        fields = (
            "id", "chore", "assignment", "occurrence", "status",
            "submitted_at", "submitter", "reviewer_detail", "reviewed_at",
        )
        read_only_fields = fields

    def get_submitter(self, obj):
        return {"membership_id": obj.submitted_by_id, "username": obj.submitted_by.user.username}

    def get_reviewer_detail(self, obj):
        if not obj.reviewer_id:
            return None
        return {"membership_id": obj.reviewer_id, "username": obj.reviewer.user.username}


class CompletionSubmissionSerializer(serializers.Serializer):
    chore = serializers.PrimaryKeyRelatedField(queryset=Chore.objects.all(), required=False)
    occurrence = serializers.UUIDField()

    def validate(self, attrs):
        membership = self.context["membership"]
        if attrs.get("chore") and attrs["chore"].household_id != membership.household_id:
            raise serializers.ValidationError({"chore": "Chore was not found."})
        return attrs


class CompletionReviewSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=(Completion.Status.APPROVED, Completion.Status.REJECTED))
