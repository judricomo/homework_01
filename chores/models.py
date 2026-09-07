from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models


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

    DIFFICULTY_POINTS = CHORE_DIFFICULTY_POINTS

    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name="chores",
    )
    name = models.CharField(max_length=255)
    difficulty = models.CharField(max_length=6, choices=Difficulty.choices)
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
        ]

    def clean(self):
        super().clean()
        if not self.name or not self.name.strip():
            raise ValidationError({"name": "Chore name cannot be blank."})

        if self.difficulty not in self.Difficulty.values:
            return

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
