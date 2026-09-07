from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.db import IntegrityError, transaction
import uuid


CHORE_DIFFICULTY_POINTS = {
    "easy": 1,
    "medium": 3,
    "hard": 5,
}


class Household(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if not self.name or not self.name.strip():
            raise ValidationError({"name": "Household name cannot be blank."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Membership(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrator"
        MEMBER = "member", "Member"

    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.OneToOneField(
        get_user_model(),
        on_delete=models.CASCADE,
        related_name="household_membership",
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.role not in self.Role.values:
            raise ValidationError({"role": "Select a valid membership role."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user} - {self.household} ({self.role})"


class Chore(models.Model):
    class Difficulty(models.TextChoices):
        EASY = "easy", "Easy"
        MEDIUM = "medium", "Medium"
        HARD = "hard", "Hard"

    class AssignmentMode(models.TextChoices):
        MANUAL = "manual", "Manual"
        ROTATION = "rotation", "Rotation"
        CLAIM = "claim", "Claim"

    DIFFICULTY_POINTS = CHORE_DIFFICULTY_POINTS

    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name="chores",
    )
    name = models.CharField(max_length=255)
    difficulty = models.CharField(max_length=6, choices=Difficulty.choices)
    assignment_mode = models.CharField(
        max_length=8, choices=AssignmentMode.choices
    )
    points = models.PositiveSmallIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(name__regex=r"^\s*$"),
                name="chore_name_not_blank",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    *[
                        models.Q(difficulty=difficulty, points=points)
                        for difficulty, points in CHORE_DIFFICULTY_POINTS.items()
                    ],
                    _connector=models.Q.OR,
                ),
                name="chore_points_match_difficulty",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    assignment_mode__in=("manual", "rotation", "claim")
                ),
                name="chore_assignment_mode_allowed_values",
            ),
        ]

    def clean(self):
        super().clean()
        if not self.name or not self.name.strip():
            raise ValidationError({"name": "Chore name cannot be blank."})

        if self.assignment_mode not in self.AssignmentMode.values:
            raise ValidationError({"assignment_mode": "Select a valid assignment mode."})
        if self.difficulty not in self.Difficulty.values:
            return
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            active = ChoreAssignment.objects.filter(chore=self, is_active=True)
            incompatible = active.exclude(
                assignment_type=self.assignment_mode
            )
            if incompatible.exists():
                raise ValidationError(
                    {"assignment_mode": "Cannot change mode while active assignments conflict."}
                )

        expected_points = self.DIFFICULTY_POINTS[self.difficulty]
        if self.pk:
            previous = (
                type(self).objects.filter(pk=self.pk)
                .values("difficulty", "points")
                .first()
            )
            difficulty_changed = (
                previous is not None and previous["difficulty"] != self.difficulty
            )
        else:
            difficulty_changed = False

        if self.points not in (0, expected_points) and not difficulty_changed:
            raise ValidationError(
                {"points": "Points must match the selected difficulty."}
            )

    def save(self, *args, **kwargs):
        self.full_clean(validate_constraints=False)
        self.points = self.DIFFICULTY_POINTS[self.difficulty]
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def active_assignment(self):
        return self.assignments.filter(is_active=True).first()

    @property
    def is_unclaimed(self):
        return (
            self.assignment_mode == self.AssignmentMode.CLAIM
            and self.active_assignment is None
        )


class RotationMember(models.Model):
    chore = models.ForeignKey(Chore, on_delete=models.CASCADE, related_name="rotation_members")
    membership = models.ForeignKey(
        Membership, on_delete=models.CASCADE, related_name="rotation_memberships"
    )
    position = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["chore", "position"], name="unique_chore_rotation_position"),
            models.UniqueConstraint(fields=["chore", "membership"], name="unique_chore_rotation_member"),
        ]
        ordering = ["position"]

    def clean(self):
        super().clean()
        if self.membership.household_id != self.chore.household_id:
            raise ValidationError({"membership": "Member must belong to the chore household."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class ChoreAssignment(models.Model):
    class AssignmentType(models.TextChoices):
        MANUAL = Chore.AssignmentMode.MANUAL, "Manual"
        CLAIM = Chore.AssignmentMode.CLAIM, "Claim"
        ROTATION = Chore.AssignmentMode.ROTATION, "Rotation"

    chore = models.ForeignKey(Chore, on_delete=models.CASCADE, related_name="assignments")
    membership = models.ForeignKey(
        Membership, on_delete=models.CASCADE, related_name="chore_assignments"
    )
    occurrence = models.UUIDField(default=uuid.uuid4, editable=False)
    assignment_type = models.CharField(max_length=8, choices=AssignmentType.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["chore", "occurrence"],
                condition=models.Q(is_active=True),
                name="unique_active_chore_occurrence_assignment",
            )
        ]

    def clean(self):
        super().clean()
        if self.assignment_type not in self.AssignmentType.values:
            raise ValidationError({"assignment_type": "Select a valid assignment type."})
        if self.membership.household_id != self.chore.household_id:
            raise ValidationError({"membership": "Member must belong to the chore household."})
        if not self.membership.is_active:
            raise ValidationError({"membership": "Member must be active."})
        if self.assignment_type != self.chore.assignment_mode:
            raise ValidationError(
                {"assignment_type": "Assignment type must match the chore assignment mode."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @classmethod
    def create_manual(cls, chore, membership, *, occurrence=None):
        if chore.assignment_mode != Chore.AssignmentMode.MANUAL:
            raise ValidationError("Manual assignments are only valid for manual chores.")
        return cls.objects.create(
            chore=chore,
            membership=membership,
            occurrence=occurrence or uuid.uuid4(),
            assignment_type=cls.AssignmentType.MANUAL,
        )

    @classmethod
    def claim(cls, chore, membership, *, occurrence=None):
        if chore.assignment_mode != Chore.AssignmentMode.CLAIM:
            raise ValidationError("Claims are only valid for claim-mode chores.")
        if occurrence is None:
            existing = cls.objects.filter(chore=chore, is_active=True).first()
            occurrence = existing.occurrence if existing else uuid.uuid4()
        try:
            with transaction.atomic():
                return cls.objects.create(
                    chore=chore,
                    membership=membership,
                    occurrence=occurrence,
                    assignment_type=cls.AssignmentType.CLAIM,
                )
        except IntegrityError as exc:
            raise ValidationError("This chore occurrence has already been claimed.") from exc
