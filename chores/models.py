from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, close_old_connections, connection, models, transaction
from django.db.models import F, Sum
from django.conf import settings
from django.utils import timezone
from datetime import date, timedelta
from zoneinfo import ZoneInfo
import time
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
        result = super().save(*args, **kwargs)
        MemberStreak.objects.get_or_create(membership=self)
        return result

    def __str__(self):
        return f"{self.user} - {self.household} ({self.role})"

    @property
    def total_points(self):
        return PointsLedger.total_for_member(self)


class Chore(models.Model):
    class Difficulty(models.TextChoices):
        EASY = "easy", "Easy"
        MEDIUM = "medium", "Medium"
        HARD = "hard", "Hard"

    class AssignmentMode(models.TextChoices):
        MANUAL = "manual", "Manual"
        ROTATION = "rotation", "Rotation"
        CLAIM = "claim", "Claim"

    class RecurrenceMode(models.TextChoices):
        FIXED = "fixed", "Fixed/calendar"
        FLEXIBLE = "flexible", "Flexible"

    class FixedRecurrence(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        EVERY_N_DAYS = "every_n_days", "Every N days"
        SELECTED_WEEKDAYS = "selected_weekdays", "Selected weekdays"

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
    recurrence_mode = models.CharField(
        max_length=8, choices=RecurrenceMode.choices, default=RecurrenceMode.FIXED
    )
    fixed_recurrence = models.CharField(
        max_length=18,
        choices=FixedRecurrence.choices,
        default=FixedRecurrence.DAILY,
        blank=True,
    )
    recurrence_interval_days = models.PositiveIntegerField(default=1)
    selected_weekdays = models.JSONField(default=list, blank=True)
    anchor_date = models.DateField(default=timezone.localdate)
    points = models.PositiveSmallIntegerField(default=0, editable=False)
    rotation_position = models.PositiveIntegerField(default=1)
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
        if self.recurrence_mode not in self.RecurrenceMode.values:
            raise ValidationError({"recurrence_mode": "Select a valid recurrence mode."})
        if not self.anchor_date:
            raise ValidationError({"anchor_date": "An anchor date is required."})
        if self.recurrence_interval_days is None or (
            isinstance(self.recurrence_interval_days, bool)
            or not isinstance(self.recurrence_interval_days, int)
            or self.recurrence_interval_days < 1
        ):
            raise ValidationError(
                {"recurrence_interval_days": "The interval must be a positive whole number."}
            )
        if self.recurrence_mode == self.RecurrenceMode.FIXED:
            if self.fixed_recurrence not in self.FixedRecurrence.values:
                raise ValidationError({"fixed_recurrence": "Select a valid fixed recurrence."})
            if self.fixed_recurrence in (
                self.FixedRecurrence.DAILY,
                self.FixedRecurrence.WEEKLY,
                self.FixedRecurrence.SELECTED_WEEKDAYS,
            ) and self.recurrence_interval_days != 1:
                raise ValidationError(
                    {"recurrence_interval_days": "This fixed recurrence uses an interval of 1."}
                )
            if self.fixed_recurrence != self.FixedRecurrence.EVERY_N_DAYS and (
                self.fixed_recurrence != self.FixedRecurrence.SELECTED_WEEKDAYS
                and self.recurrence_interval_days != 1
            ):
                raise ValidationError({"recurrence_interval_days": "This recurrence does not use an interval."})
            if self.fixed_recurrence == self.FixedRecurrence.SELECTED_WEEKDAYS:
                if not isinstance(self.selected_weekdays, list) or not self.selected_weekdays:
                    raise ValidationError({"selected_weekdays": "Select at least one weekday."})
                if any(
                    isinstance(day, bool) or not isinstance(day, int) or day not in range(7)
                    for day in self.selected_weekdays
                ):
                    raise ValidationError({"selected_weekdays": "Weekdays must be integers from 0 through 6."})
            elif self.selected_weekdays:
                raise ValidationError({"selected_weekdays": "Selected weekdays require weekday recurrence."})
        else:
            if self.recurrence_interval_days < 1:
                raise ValidationError(
                    {"recurrence_interval_days": "The interval must be a positive whole number."}
                )
            if self.fixed_recurrence != self.FixedRecurrence.DAILY:
                raise ValidationError({"fixed_recurrence": "Flexible recurrence cannot define a fixed rule."})
            if self.selected_weekdays:
                raise ValidationError({"selected_weekdays": "Flexible recurrence cannot define weekdays."})
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

    def next_due_date(self, prior_due_date=None, completions=()):
        """Return the next due local date using the configured project timezone.

        ``completions`` is intentionally an iterable contract for the completion
        workflow: approved records must expose ``chore``, ``household``, an
        approved status (``status == "approved"`` or ``is_approved``), and a
        timezone-aware ``completed_at`` (or ``approved_at``) value.
        """
        if prior_due_date is None:
            if self.recurrence_mode == self.RecurrenceMode.FLEXIBLE:
                approved = self._approved_completion_dates(completions)
                if approved:
                    return max(approved) + timedelta(days=self.recurrence_interval_days)
            return self.anchor_date

        if not isinstance(prior_due_date, date):
            raise TypeError("prior_due_date must be a local date")
        if self.recurrence_mode == self.RecurrenceMode.FLEXIBLE:
            approved = self._approved_completion_dates(completions)
            return (
                max(approved) + timedelta(days=self.recurrence_interval_days)
                if approved
                else self.anchor_date
            )
        if self.fixed_recurrence == self.FixedRecurrence.DAILY:
            return prior_due_date + timedelta(days=1)
        if self.fixed_recurrence == self.FixedRecurrence.WEEKLY:
            return prior_due_date + timedelta(days=7)
        if self.fixed_recurrence == self.FixedRecurrence.EVERY_N_DAYS:
            return prior_due_date + timedelta(days=self.recurrence_interval_days)
        selected = set(self.selected_weekdays)
        for offset in range(1, 8):
            candidate = prior_due_date + timedelta(days=offset)
            if candidate.weekday() in selected:
                return candidate
        raise ValidationError("Selected weekdays must contain a valid weekday.")

    calculate_next_due_date = next_due_date

    def _approved_completion_dates(self, completions):
        project_zone = ZoneInfo(settings.TIME_ZONE)
        dates = []
        for completion in completions or ():
            if getattr(completion, "chore_id", getattr(getattr(completion, "chore", None), "pk", None)) != self.pk:
                continue
            household_id = getattr(
                completion, "household_id",
                getattr(getattr(completion, "household", None), "pk", None),
            )
            if household_id != self.household_id:
                continue
            status = getattr(completion, "status", None)
            if status is not None and status != "approved":
                continue
            if status is None and not getattr(completion, "is_approved", False):
                continue
            completed_at = getattr(completion, "completed_at", None) or getattr(
                completion, "approved_at", None
            )
            if completed_at is None:
                continue
            if isinstance(completed_at, date) and not hasattr(completed_at, "hour"):
                dates.append(completed_at)
            else:
                dates.append(timezone.localtime(completed_at, project_zone).date())
        return dates

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
    SQLITE_LOCK_RETRIES = 5
    SQLITE_LOCK_RETRY_DELAY = 0.02

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
        for attempt in range(cls.SQLITE_LOCK_RETRIES + 1):
            try:
                with transaction.atomic():
                    # SQLite does not implement SELECT FOR UPDATE. A no-op
                    # update obtains its write lock before the occurrence is
                    # selected, so concurrent first claims serialize safely.
                    chore_row = Chore.objects.select_for_update().get(pk=chore.pk)
                    if connection.vendor == "sqlite":
                        Chore.objects.filter(pk=chore_row.pk).update(name=F("name"))
                    claim_occurrence = occurrence
                    if claim_occurrence is None:
                        existing = cls.objects.filter(
                            chore=chore_row, is_active=True
                        ).first()
                        claim_occurrence = (
                            existing.occurrence if existing else uuid.uuid4()
                        )
                    return cls.objects.create(
                        chore=chore_row,
                        membership=membership,
                        occurrence=claim_occurrence,
                        assignment_type=cls.AssignmentType.CLAIM,
                    )
            except IntegrityError as exc:
                raise ValidationError(
                    "This chore occurrence has already been claimed."
                ) from exc
            except OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt == cls.SQLITE_LOCK_RETRIES:
                    raise ValidationError(
                        "This chore occurrence could not be claimed due to concurrent activity."
                    ) from exc
                time.sleep(cls.SQLITE_LOCK_RETRY_DELAY * (attempt + 1))

    @classmethod
    def schedule_rotation(cls, chore, occurrence):
        """Assign one due occurrence to the next eligible rotation member."""
        if chore.assignment_mode != Chore.AssignmentMode.ROTATION:
            raise ValidationError(
                "Rotation scheduling is only valid for rotation-mode chores."
            )
        if occurrence is None:
            raise ValidationError("A due occurrence is required.")

        for attempt in range(cls.SQLITE_LOCK_RETRIES + 1):
            try:
                with transaction.atomic():
                    chore_row = Chore.objects.select_for_update().get(
                        pk=chore.pk,
                        household_id=chore.household_id,
                        assignment_mode=Chore.AssignmentMode.ROTATION,
                    )
                    if connection.vendor == "sqlite":
                        Chore.objects.filter(pk=chore_row.pk).update(name=F("name"))

                    existing = cls.objects.filter(
                        chore=chore_row, occurrence=occurrence, is_active=True
                    ).first()
                    if existing:
                        return existing

                    members = list(
                        RotationMember.objects.filter(
                            chore=chore_row,
                            is_active=True,
                            membership__household_id=chore_row.household_id,
                        ).order_by("position", "pk")
                    )
                    if not members:
                        return None

                    start = next(
                        (
                            index
                            for index, member in enumerate(members)
                            if member.position >= chore_row.rotation_position
                        ),
                        0,
                    )
                    selected = next(
                        (
                            (index, members[index])
                            for offset in range(len(members))
                            for index in [(start + offset) % len(members)]
                            if members[index].membership.is_active
                        ),
                        None,
                    )
                    if selected is None:
                        return None

                    index, rotation_member = selected
                    assignment = cls.objects.create(
                        chore=chore_row,
                        membership=rotation_member.membership,
                        occurrence=occurrence,
                        assignment_type=cls.AssignmentType.ROTATION,
                    )
                    next_member = members[(index + 1) % len(members)]
                    chore_row.rotation_position = next_member.position
                    chore_row.save(update_fields=["rotation_position", "updated_at"])
                    return assignment
            except IntegrityError:
                existing = cls.objects.filter(
                    chore=chore, occurrence=occurrence, is_active=True
                ).first()
                if existing:
                    return existing
                raise ValidationError(
                    "This chore occurrence could not be scheduled concurrently."
                )
            except OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt == cls.SQLITE_LOCK_RETRIES:
                    raise ValidationError(
                        "This chore occurrence could not be scheduled due to concurrent activity."
                    ) from exc
                time.sleep(cls.SQLITE_LOCK_RETRY_DELAY * (attempt + 1))


class Completion(models.Model):
    """Immutable self-reported history; rejected attempts are never mutated or retried."""
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="completions")
    chore = models.ForeignKey(Chore, on_delete=models.CASCADE, related_name="completions")
    assignment = models.ForeignKey(
        ChoreAssignment, on_delete=models.PROTECT, related_name="completions"
    )
    submitted_by = models.ForeignKey(
        Membership, on_delete=models.PROTECT, related_name="submitted_completions"
    )
    occurrence = models.UUIDField()
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewer = models.ForeignKey(
        Membership, null=True, blank=True, on_delete=models.PROTECT,
        related_name="reviewed_completions",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["chore", "occurrence"],
                condition=models.Q(status__in=("pending", "approved")),
                name="unique_open_completion_occurrence",
            ),
            models.UniqueConstraint(
                fields=["chore", "occurrence", "submitted_by"],
                condition=models.Q(status="rejected"),
                name="unique_rejected_completion_submitter",
            ),
        ]
        ordering = ["-submitted_at", "-pk"]

    def clean(self):
        super().clean()
        if self.household_id != self.chore.household_id:
            raise ValidationError({"household": "Completion household must match the chore."})
        if self.assignment.chore_id != self.chore_id or self.assignment.occurrence != self.occurrence:
            raise ValidationError({"occurrence": "Completion must match its assignment occurrence."})
        if self.submitted_by.household_id != self.household_id or not self.submitted_by.is_active:
            raise ValidationError({"submitted_by": "Submitter must be an active household member."})
        if self.status != self.Status.PENDING and (not self.reviewer or not self.reviewed_at):
            raise ValidationError({"reviewer": "Finalized completions require review history."})

    @classmethod
    def submit(cls, *, membership, chore, occurrence):
        if not membership.is_active or membership.household_id != chore.household_id:
            raise ValidationError("An active household member is required.")
        with transaction.atomic():
            assignment = (
                ChoreAssignment.objects.select_for_update()
                .filter(chore=chore, occurrence=occurrence, is_active=True)
                .select_related("membership")
                .first()
            )
            if not assignment or assignment.membership.household_id != membership.household_id:
                raise ValidationError("This occurrence is not available to you.")
            if assignment.membership_id != membership.id:
                raise ValidationError("You are not eligible to complete this occurrence.")
            if cls.objects.filter(chore=chore, occurrence=occurrence, status__in=("pending", "approved")).exists():
                raise ValidationError("This occurrence already has a completion.")
            if cls.objects.filter(
                chore=chore, occurrence=occurrence, submitted_by=membership, status="rejected"
            ).exists():
                raise ValidationError("You already submitted and were rejected for this occurrence.")
            try:
                return cls.objects.create(
                    household=membership.household,
                    chore=chore,
                    assignment=assignment,
                    submitted_by=membership,
                    occurrence=occurrence,
                )
            except IntegrityError as exc:
                raise ValidationError("This occurrence already has a completion.") from exc

    @classmethod
    def review(cls, *, completion_id, reviewer, status):
        if status not in (cls.Status.APPROVED, cls.Status.REJECTED):
            raise ValidationError("Review status must be approved or rejected.")
        with transaction.atomic():
            completion = cls.objects.select_for_update().select_related(
                "chore", "assignment", "submitted_by"
            ).get(pk=completion_id)
            if not reviewer.is_active or reviewer.household_id != completion.household_id:
                raise ValidationError("Reviewer must be an active household member.")
            if reviewer.id == completion.submitted_by_id:
                raise ValidationError("You cannot review your own completion.")
            if completion.status != cls.Status.PENDING:
                raise ValidationError("This completion has already been reviewed.")
            reviewed_at = timezone.now()
            updated = cls.objects.filter(
                pk=completion.pk, status=cls.Status.PENDING
            ).update(status=status, reviewer=reviewer, reviewed_at=reviewed_at)
            if not updated:
                raise ValidationError("This completion has already been reviewed.")
            completion.refresh_from_db()
            if status == cls.Status.APPROVED:
                completion.assignment.is_active = False
                completion.assignment.save(update_fields=["is_active"])
                MemberStreak.record_approved_completion(completion)
            return completion


class MemberStreak(models.Model):
    """Durable daily activity evidence and derived streak state for one member."""

    membership = models.OneToOneField(
        Membership, on_delete=models.CASCADE, related_name="streak"
    )
    current_streak = models.PositiveIntegerField(default=0)
    best_streak = models.PositiveIntegerField(default=0)
    last_activity_date = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(current_streak__gte=0) & models.Q(best_streak__gte=0),
                name="member_streak_non_negative",
            ),
        ]

    @classmethod
    def activity_date_for(cls, submitted_at):
        if submitted_at is None:
            raise ValidationError("A submitted timestamp is required.")
        if timezone.is_naive(submitted_at):
            submitted_at = timezone.make_aware(submitted_at, timezone.utc)
        return timezone.localtime(submitted_at, ZoneInfo(settings.TIME_ZONE)).date()

    @classmethod
    def record_approved_completion(cls, completion):
        """Record one approved completion's local member-day and recalculate state."""
        if not isinstance(completion, Completion):
            completion = Completion.objects.select_related(
                "household", "submitted_by", "chore"
            ).get(pk=completion)
        if completion.status != Completion.Status.APPROVED:
            raise ValidationError("Only approved completions affect streaks.")
        if (
            completion.submitted_at is None
            or completion.household_id != completion.chore.household_id
            or completion.submitted_by.household_id != completion.household_id
            or not completion.submitted_by.is_active
        ):
            raise ValidationError("Completion is not valid for streak tracking.")

        activity_date = cls.activity_date_for(completion.submitted_at)
        for attempt in range(PointsLedger.SQLITE_LOCK_RETRIES + 1):
            try:
                with transaction.atomic():
                    membership = Membership.objects.select_for_update().get(
                        pk=completion.submitted_by_id,
                        household_id=completion.household_id,
                        is_active=True,
                    )
                    streak, _ = cls.objects.select_for_update().get_or_create(
                        membership=membership
                    )
                    try:
                        with transaction.atomic():
                            MemberActivityDay.objects.create(
                                membership=membership,
                                household=membership.household,
                                activity_date=activity_date,
                            )
                    except (IntegrityError, ValidationError):
                        if not MemberActivityDay.objects.filter(
                            membership=membership, activity_date=activity_date
                        ).exists():
                            raise
                    days = list(
                        MemberActivityDay.objects.filter(
                            membership=membership,
                            household_id=membership.household_id,
                        ).values_list("activity_date", flat=True).order_by("activity_date")
                    )
                    current = best = run = 0
                    previous = None
                    for day in days:
                        run = run + 1 if previous and day == previous + timedelta(days=1) else 1
                        best = max(best, run)
                        previous = day
                    if days:
                        latest = days[-1]
                        run = 0
                        day = latest
                        while day in days:
                            run += 1
                            day -= timedelta(days=1)
                        current = run
                    streak.current_streak = current
                    streak.best_streak = max(streak.best_streak, best)
                    streak.last_activity_date = days[-1] if days else None
                    streak.save(update_fields=[
                        "current_streak", "best_streak", "last_activity_date", "updated_at"
                    ])
                    return streak
            except OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt == PointsLedger.SQLITE_LOCK_RETRIES:
                    raise ValidationError("Streak could not be updated due to concurrent activity.") from exc
                close_old_connections()
                time.sleep(PointsLedger.SQLITE_LOCK_RETRY_DELAY * (attempt + 1))

    update_for_approved_completion = record_approved_completion


class MemberActivityDay(models.Model):
    membership = models.ForeignKey(
        Membership, on_delete=models.CASCADE, related_name="activity_days"
    )
    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="member_activity_days"
    )
    activity_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["activity_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "activity_date"],
                name="unique_member_activity_day",
            ),
        ]

    def clean(self):
        super().clean()
        if self.membership.household_id != self.household_id:
            raise ValidationError({"household": "Activity household must match membership."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class PointsLedger(models.Model):
    SQLITE_LOCK_RETRIES = 5
    SQLITE_LOCK_RETRY_DELAY = 0.02

    household = models.ForeignKey(
        Household, on_delete=models.PROTECT, related_name="points_ledger_entries"
    )
    member = models.ForeignKey(
        Membership, on_delete=models.PROTECT, related_name="points_ledger_entries"
    )
    chore = models.ForeignKey(
        Chore, on_delete=models.PROTECT, related_name="points_ledger_entries"
    )
    completion = models.OneToOneField(
        Completion, on_delete=models.PROTECT, related_name="points_ledger_entry"
    )
    points = models.PositiveSmallIntegerField()
    awarded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-awarded_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["completion"],
                name="unique_points_ledger_completion",
            )
        ]

    def clean(self):
        super().clean()
        if self.completion_id is not None:
            if self.household_id != self.completion.household_id:
                raise ValidationError({"household": "Award household must match the completion."})
            if self.member_id is not None and self.member.household_id != self.household_id:
                raise ValidationError({"member": "Member must belong to the awarding household."})
            if self.member_id is not None and self.member_id != self.completion.submitted_by_id:
                raise ValidationError({"member": "Member must match the completion submitter."})
            if self.chore_id is not None and self.chore.household_id != self.household_id:
                raise ValidationError({"chore": "Chore must belong to the awarding household."})
            if self.chore_id is not None and self.chore_id != self.completion.chore_id:
                raise ValidationError({"chore": "Chore must match the completion chore."})

    def save(self, *args, **kwargs):
        if self.pk:
            current = type(self).objects.filter(pk=self.pk).values(
                "household_id",
                "member_id",
                "chore_id",
                "completion_id",
                "points",
                "awarded_at",
            ).first()
            if current:
                for field_name, expected in (
                    ("household_id", self.household_id),
                    ("member_id", self.member_id),
                    ("chore_id", self.chore_id),
                    ("completion_id", self.completion_id),
                    ("points", self.points),
                    ("awarded_at", self.awarded_at),
                ):
                    if current.get(field_name) != expected:
                        raise ValidationError("Points ledger entries are immutable.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Points ledger entries cannot be deleted.")

    @staticmethod
    def _coerce_completion(value):
        if value is None:
            raise ValidationError("A completion is required.")
        if isinstance(value, Completion):
            return value
        return Completion.objects.select_related("household", "chore", "submitted_by").get(pk=value)

    @classmethod
    def award_for_completion(cls, completion):
        completion = cls._coerce_completion(completion)
        for attempt in range(cls.SQLITE_LOCK_RETRIES + 1):
            try:
                with transaction.atomic():
                    completion_row = Completion.objects.select_related(
                        "household",
                        "chore",
                        "submitted_by",
                    ).get(pk=completion.pk)
                    if completion_row.status != Completion.Status.APPROVED:
                        raise ValidationError("Only approved completions can be awarded points.")

                    existing = cls.objects.filter(completion_id=completion_row.pk).first()
                    if existing is not None:
                        return existing

                    chore_row = Chore.objects.get(pk=completion_row.chore_id)
                    if completion_row.household_id != chore_row.household_id:
                        raise ValidationError("Completion household must match the chore household.")
                    if completion_row.submitted_by.household_id != completion_row.household_id:
                        raise ValidationError("Submitter must belong to the completion household.")

                    try:
                        return cls.objects.create(
                            household=completion_row.household,
                            member=completion_row.submitted_by,
                            chore=chore_row,
                            completion=completion_row,
                            points=int(chore_row.points),
                            awarded_at=timezone.now(),
                        )
                    except IntegrityError:
                        existing = cls.objects.filter(completion_id=completion_row.pk).first()
                        if existing is not None:
                            return existing
                        raise
            except IntegrityError:
                close_old_connections()
                if attempt == cls.SQLITE_LOCK_RETRIES:
                    raise ValidationError(
                        "This completion could not be awarded due to concurrent activity."
                    )
                time.sleep(cls.SQLITE_LOCK_RETRY_DELAY * (attempt + 1))
            except OperationalError as exc:
                close_old_connections()
                if "locked" not in str(exc).lower() or attempt == cls.SQLITE_LOCK_RETRIES:
                    raise ValidationError(
                        "This completion could not be awarded due to concurrent activity."
                    ) from exc
                time.sleep(cls.SQLITE_LOCK_RETRY_DELAY * (attempt + 1))

    award_completion = award_for_completion
    process_completion = award_for_completion
    create_for_completion = award_for_completion

    @classmethod
    def total_for_member(cls, member):
        return (
            cls.objects.filter(member=member).aggregate(total=Sum("points"))["total"] or 0
        )

    score_for_member = total_for_member

    @classmethod
    def total_for_household(cls, household):
        rows = cls.objects.filter(household=household).values_list("member_id", "points")
        totals = {}
        for member_id, points in rows:
            totals[member_id] = totals.get(member_id, 0) + points
        return totals
