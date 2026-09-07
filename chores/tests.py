import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, close_old_connections, transaction
from django.test import SimpleTestCase
from django.test import TestCase, TransactionTestCase
from django.urls import path, reverse
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework.views import APIView

from .models import (
    BadgeAward,
    BadgeCatalog,
    Chore,
    ChoreAssignment,
    Completion,
    Household,
    MemberActivityDay,
    MemberStreak,
    Membership,
    PointsLedger,
    RotationMember,
)
from .services import calculate_next_due_date


class ProjectLoadsTest(SimpleTestCase):
    def test_admin_login_page_loads(self):
        response = self.client.get(reverse("admin:login"))

        self.assertEqual(response.status_code, 200)


class ChoreRecurrenceTests(TestCase):
    def setUp(self):
        self.household = Household.objects.create(name="Recurrence household")
        self.chore = Chore.objects.create(
            household=self.household,
            name="Clean kitchen",
            difficulty=Chore.Difficulty.EASY,
            assignment_mode=Chore.AssignmentMode.MANUAL,
            anchor_date=date(2026, 3, 1),
        )

    def completion(self, **kwargs):
        values = dict(
            chore_id=self.chore.pk,
            household_id=self.household.pk,
            status="approved",
            completed_at=timezone.make_aware(datetime(2026, 3, 8, 23, 30)),
        )
        values.update(kwargs)
        return SimpleNamespace(**values)

    def test_fixed_rules_and_first_due_date(self):
        self.assertEqual(self.chore.next_due_date(), date(2026, 3, 1))
        self.chore.fixed_recurrence = Chore.FixedRecurrence.WEEKLY
        self.assertEqual(self.chore.next_due_date(date(2026, 3, 1)), date(2026, 3, 8))
        self.chore.fixed_recurrence = Chore.FixedRecurrence.EVERY_N_DAYS
        self.chore.recurrence_interval_days = 3
        self.assertEqual(self.chore.next_due_date(date(2026, 3, 1)), date(2026, 3, 4))

    def test_selected_weekdays_wrap_and_skip_to_next(self):
        self.chore.fixed_recurrence = Chore.FixedRecurrence.SELECTED_WEEKDAYS
        self.chore.selected_weekdays = [0]
        self.chore.full_clean()
        self.assertEqual(self.chore.next_due_date(date(2026, 3, 6)), date(2026, 3, 9))

    def test_flexible_uses_latest_approved_completion_only(self):
        self.chore.recurrence_mode = Chore.RecurrenceMode.FLEXIBLE
        self.chore.recurrence_interval_days = 2
        self.chore.save()
        pending = self.completion(status="pending", completed_at=datetime(2026, 3, 20))
        rejected = self.completion(status="rejected", completed_at=datetime(2026, 3, 19))
        other = self.completion(chore_id=999, completed_at=datetime(2026, 3, 18))
        self.assertEqual(
            calculate_next_due_date(self.chore, completions=[pending, rejected, other, self.completion()]),
            date(2026, 3, 10),
        )

    def test_flexible_converts_aware_completion_in_project_timezone(self):
        self.chore.recurrence_mode = Chore.RecurrenceMode.FLEXIBLE
        self.chore.recurrence_interval_days = 1
        self.chore.save()
        completion = self.completion(
            completed_at=datetime.fromisoformat("2026-03-09T06:30:00+00:00")
        )
        with self.settings(TIME_ZONE="America/Los_Angeles"):
            self.assertEqual(self.chore.next_due_date(completions=[completion]), date(2026, 3, 9))

    def test_invalid_recurrence_values_are_rejected(self):
        self.chore.recurrence_interval_days = 0
        with self.assertRaises(ValidationError):
            self.chore.full_clean()
        self.chore.recurrence_interval_days = 1
        self.chore.fixed_recurrence = Chore.FixedRecurrence.SELECTED_WEEKDAYS
        self.chore.selected_weekdays = []
        with self.assertRaises(ValidationError):
            self.chore.full_clean()


class HouseholdMembershipTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.household = Household.objects.create(name="My household")
        self.user = self.user_model.objects.create_user(
            username="member",
            password="password",
        )

    def test_household_and_membership_can_be_created(self):
        membership = Membership.objects.create(
            household=self.household,
            user=self.user,
            role=Membership.Role.MEMBER,
        )

        self.assertEqual(self.household.memberships.get(), membership)
        self.assertEqual(self.user.household_membership, membership)
        self.assertEqual(membership.role, Membership.Role.MEMBER)

    def test_household_requires_a_non_blank_name(self):
        household = Household(name=" ")

        with self.assertRaises(ValidationError):
            household.full_clean()

    def test_invalid_membership_role_is_rejected(self):
        membership = Membership(
            household=self.household,
            user=self.user,
            role="owner",
        )

        with self.assertRaises(ValidationError):
            membership.full_clean()

    def test_user_can_have_only_one_membership(self):
        Membership.objects.create(
            household=self.household,
            user=self.user,
            role=Membership.Role.MEMBER,
        )
        other_household = Household.objects.create(name="Other household")

        with self.assertRaises((ValidationError, IntegrityError)):
            Membership.objects.create(
                household=other_household,
                user=self.user,
                role=Membership.Role.MEMBER,
            )

    def test_household_can_have_multiple_members_with_different_roles(self):
        admin = self.user_model.objects.create_user(
            username="admin",
            password="password",
        )
        Membership.objects.create(
            household=self.household,
            user=admin,
            role=Membership.Role.ADMIN,
        )
        member = Membership.objects.create(
            household=self.household,
            user=self.user,
            role=Membership.Role.MEMBER,
        )

        self.assertEqual(self.household.memberships.count(), 2)
        self.assertEqual(
            self.household.memberships.get(user=admin).role,
            Membership.Role.ADMIN,
        )
        self.assertEqual(member.role, Membership.Role.MEMBER)

    def test_deleting_user_cascades_to_membership(self):
        membership = Membership.objects.create(
            household=self.household,
            user=self.user,
            role=Membership.Role.MEMBER,
        )

        self.user.delete()

        self.assertFalse(Membership.objects.filter(pk=membership.pk).exists())

    def test_deleting_household_cascades_to_memberships(self):
        membership = Membership.objects.create(
            household=self.household,
            user=self.user,
            role=Membership.Role.MEMBER,
        )

        self.household.delete()

        self.assertFalse(Membership.objects.filter(pk=membership.pk).exists())


class MembershipManagementAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_model = get_user_model()
        self.household = Household.objects.create(name="Admin household")
        self.admin = self.user_model.objects.create_user(
            username="administrator", email="ADMIN@example.com"
        )
        self.admin_membership = Membership.objects.create(
            household=self.household, user=self.admin, role=Membership.Role.ADMIN
        )
        self.list_url = reverse("membership-list")
        self.client.force_authenticate(self.admin)

    def add_user(self, username, email):
        return self.user_model.objects.create_user(username=username, email=email)

    def test_admin_can_add_member_with_normalized_email_and_response(self):
        user = self.add_user("new-member", "new@example.com")

        response = self.client.post(
            self.list_url, {"email": "  NEW@EXAMPLE.COM "}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        membership = Membership.objects.get(user=user)
        self.assertEqual(membership.role, Membership.Role.MEMBER)
        self.assertEqual(response.data["user"]["id"], user.id)
        self.assertEqual(response.data["household"]["id"], self.household.id)
        self.assertEqual(response.data["role"], Membership.Role.MEMBER)

    def test_add_rejects_unknown_duplicate_and_ambiguous_emails_without_changes(self):
        before = Membership.objects.count()
        response = self.client.post(
            self.list_url, {"email": "unknown@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Membership.objects.count(), before)

        member = self.add_user("existing", "existing@example.com")
        Membership.objects.create(
            household=self.household, user=member, role=Membership.Role.MEMBER
        )
        response = self.client.post(
            self.list_url, {"email": " EXISTING@EXAMPLE.COM "}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Membership.objects.filter(user=member).count(), 1)

        self.add_user("ambiguous-one", "same@example.com")
        self.add_user("ambiguous-two", "SAME@example.com")
        response = self.client.post(
            self.list_url, {"email": "same@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Membership.objects.count(), before + 1)

    def test_admin_can_list_retrieve_change_role_and_remove_member(self):
        member = self.add_user("member", "member@example.com")
        membership = Membership.objects.create(
            household=self.household, user=member, role=Membership.Role.MEMBER
        )

        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        response = self.client.get(reverse("membership-detail", args=[membership.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.patch(
            reverse("membership-detail", args=[membership.id]),
            {"role": Membership.Role.ADMIN},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        membership.refresh_from_db()
        self.assertEqual(membership.role, Membership.Role.ADMIN)

        response = self.client.patch(
            reverse("membership-detail", args=[membership.id]),
            {"role": Membership.Role.MEMBER},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        membership.refresh_from_db()
        self.assertEqual(membership.role, Membership.Role.MEMBER)

        response = self.client.delete(
            reverse("membership-detail", args=[membership.id])
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Membership.objects.filter(pk=membership.id).exists())

    def test_last_admin_cannot_demote_or_remove_themself(self):
        detail_url = reverse("membership-detail", args=[self.admin_membership.id])
        before_count = Membership.objects.count()

        response = self.client.patch(
            detail_url, {"role": Membership.Role.MEMBER}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.admin_membership.refresh_from_db()
        self.assertEqual(self.admin_membership.role, Membership.Role.ADMIN)
        self.assertEqual(Membership.objects.count(), before_count)

        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Membership.objects.filter(pk=self.admin_membership.id).exists())
        self.assertEqual(Membership.objects.count(), before_count)

    def test_regular_member_is_forbidden_and_other_household_is_scoped_out(self):
        member = self.add_user("regular", "regular@example.com")
        membership = Membership.objects.create(
            household=self.household, user=member, role=Membership.Role.MEMBER
        )
        other_household = Household.objects.create(name="Other")
        other_admin = self.add_user("other-admin", "other@example.com")
        other_membership = Membership.objects.create(
            household=other_household, user=other_admin, role=Membership.Role.ADMIN
        )

        self.client.force_authenticate(member)
        before_count = Membership.objects.count()
        for method, url, data in (
            ("get", self.list_url, None),
            ("post", self.list_url, {"email": "regular@example.com"}),
            ("patch", reverse("membership-detail", args=[membership.id]), {"role": "admin"}),
            ("delete", reverse("membership-detail", args=[membership.id]), None),
        ):
            response = getattr(self.client, method)(url, data, format="json") if data else getattr(self.client, method)(url)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        membership.refresh_from_db()
        self.assertEqual(membership.role, Membership.Role.MEMBER)
        self.assertEqual(Membership.objects.count(), before_count)

        self.client.force_authenticate(self.admin)
        before_count = Membership.objects.count()
        response = self.client.get(
            reverse("membership-detail", args=[other_membership.id])
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Membership.objects.count(), before_count)
        other_membership.refresh_from_db()
        self.assertEqual(other_membership.role, Membership.Role.ADMIN)

    def test_unauthenticated_membership_requests_are_rejected(self):
        self.client.force_authenticate(None)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ChoreModelTests(TestCase):
    def setUp(self):
        self.household = Household.objects.create(name="Chore household")

    def test_creation_and_retrieval_derive_points_for_each_difficulty(self):
        for difficulty, points in Chore.DIFFICULTY_POINTS.items():
            chore = Chore.objects.create(
                household=self.household,
                name=f"{difficulty} chore",
                difficulty=difficulty,
                assignment_mode=Chore.AssignmentMode.MANUAL,
            )
            self.assertEqual(chore.points, points)
            self.assertEqual(Chore.objects.get(pk=chore.pk).points, points)

    def test_changing_difficulty_recalculates_points(self):
        chore = Chore.objects.create(
            household=self.household, name="Sweep", difficulty=Chore.Difficulty.EASY,
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )

        chore.difficulty = Chore.Difficulty.HARD
        chore.save()

        chore.refresh_from_db()
        self.assertEqual(chore.points, Chore.DIFFICULTY_POINTS[Chore.Difficulty.HARD])

    def test_invalid_difficulty_and_blank_name_are_rejected_without_changes(self):
        chore = Chore.objects.create(
            household=self.household, name="Wash dishes", difficulty=Chore.Difficulty.MEDIUM,
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        original = (chore.name, chore.difficulty, chore.points)

        for field, value in (("name", "  "), ("difficulty", "extreme")):
            setattr(chore, field, value)
            with self.assertRaises(ValidationError):
                chore.save()
            chore.refresh_from_db()
            self.assertEqual((chore.name, chore.difficulty, chore.points), original)

    def test_conflicting_points_are_rejected_without_changes(self):
        chore = Chore.objects.create(
            household=self.household, name="Mop", difficulty=Chore.Difficulty.EASY,
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        chore.points = 99

        with self.assertRaises(ValidationError):
            chore.save()

        chore.refresh_from_db()
        self.assertEqual(chore.points, Chore.DIFFICULTY_POINTS[Chore.Difficulty.EASY])

    def test_household_is_required_and_chore_can_be_deleted(self):
        chore = Chore(
            name="Take out trash",
            difficulty=Chore.Difficulty.EASY,
        )
        with self.assertRaises(ValidationError):
            chore.full_clean()

        chore = Chore.objects.create(
            household=self.household,
            name="Take out trash",
            difficulty=Chore.Difficulty.EASY,
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        chore.delete()
        self.assertFalse(Chore.objects.filter(pk=chore.pk).exists())


class ChoreAssignmentTests(TransactionTestCase):
    def setUp(self):
        self.household = Household.objects.create(name="Assignments")
        self.user = get_user_model().objects.create_user(username="assignable")
        self.member = Membership.objects.create(
            household=self.household, user=self.user, role=Membership.Role.MEMBER
        )
        competing_user = get_user_model().objects.create_user(username="competitor")
        self.competitor = Membership.objects.create(
            household=self.household,
            user=competing_user,
            role=Membership.Role.MEMBER,
        )
        self.other_household = Household.objects.create(name="Other")
        other_user = get_user_model().objects.create_user(username="outsider")
        self.outsider = Membership.objects.create(
            household=self.other_household, user=other_user, role=Membership.Role.MEMBER
        )

    def chore(self, mode):
        return Chore.objects.create(
            household=self.household, name=f"{mode} chore",
            difficulty=Chore.Difficulty.EASY, assignment_mode=mode,
        )

    def test_modes_are_required_and_invalid_values_rejected(self):
        chore = Chore(
            household=self.household, name="Invalid", difficulty=Chore.Difficulty.EASY,
            assignment_mode="bogus",
        )
        with self.assertRaises(ValidationError):
            chore.full_clean()
        chore.assignment_mode = None
        with self.assertRaises(ValidationError):
            chore.full_clean()

    def test_database_rejects_unknown_assignment_mode_without_model_validation(self):
        chore = self.chore(Chore.AssignmentMode.MANUAL)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Chore.objects.filter(pk=chore.pk).update(assignment_mode="bogus")

        chore.refresh_from_db()
        self.assertEqual(chore.assignment_mode, Chore.AssignmentMode.MANUAL)

    def test_manual_assignment_is_household_and_active_member_scoped(self):
        chore = self.chore(Chore.AssignmentMode.MANUAL)
        assignment = ChoreAssignment.create_manual(chore, self.member)
        self.assertEqual(assignment.membership, self.member)
        self.member.is_active = False
        self.member.save()
        with self.assertRaises(ValidationError):
            ChoreAssignment.create_manual(chore, self.member)
        with self.assertRaises(ValidationError):
            ChoreAssignment.create_manual(chore, self.outsider)
        self.assertEqual(ChoreAssignment.objects.count(), 1)

    def test_claim_is_unclaimed_then_has_one_winner(self):
        chore = self.chore(Chore.AssignmentMode.CLAIM)
        self.assertTrue(chore.is_unclaimed)
        winner = ChoreAssignment.claim(chore, self.member)
        chore.refresh_from_db()
        self.assertFalse(chore.is_unclaimed)
        self.assertEqual(chore.active_assignment, winner)
        with self.assertRaises(ValidationError):
            ChoreAssignment.claim(chore, self.member)
        self.assertEqual(ChoreAssignment.objects.count(), 1)

    def test_competing_members_cannot_claim_the_same_occurrence(self):
        chore = self.chore(Chore.AssignmentMode.CLAIM)
        occurrence = uuid.uuid4()

        winner = ChoreAssignment.claim(chore, self.member, occurrence=occurrence)
        with self.assertRaises(ValidationError):
            ChoreAssignment.claim(chore, self.competitor, occurrence=occurrence)

        self.assertEqual(
            list(
                ChoreAssignment.objects.filter(
                    chore=chore, occurrence=occurrence, is_active=True
                )
            ),
            [winner],
        )

    def test_failed_claims_do_not_create_assignments_or_change_chore_state(self):
        chore = self.chore(Chore.AssignmentMode.CLAIM)
        self.member.is_active = False
        self.member.save()
        before = (chore.assignment_mode, ChoreAssignment.objects.count())

        with self.assertRaises(ValidationError):
            ChoreAssignment.claim(chore, self.member)
        with self.assertRaises(ValidationError):
            ChoreAssignment.claim(chore, self.outsider)

        chore.refresh_from_db()
        self.assertEqual(
            (chore.assignment_mode, ChoreAssignment.objects.count()), before
        )
        self.assertIsNone(chore.active_assignment)

    def test_concurrent_competing_claims_leave_one_winner(self):
        chore = self.chore(Chore.AssignmentMode.CLAIM)
        occurrence = uuid.uuid4()
        barrier = threading.Barrier(2)

        def claim(member):
            close_old_connections()
            barrier.wait()
            try:
                return ("winner", ChoreAssignment.claim(
                    chore, member, occurrence=occurrence
                ))
            except ValidationError as exc:
                return ("conflict", str(exc))
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(claim, (self.member, self.competitor))
            )

        self.assertEqual([result[0] for result in results].count("winner"), 1)
        self.assertEqual([result[0] for result in results].count("conflict"), 1)
        self.assertEqual(
            ChoreAssignment.objects.filter(
                chore=chore, occurrence=occurrence, is_active=True
            ).count(),
            1,
        )

    def test_concurrent_first_claims_share_one_generated_occurrence(self):
        chore = self.chore(Chore.AssignmentMode.CLAIM)
        barrier = threading.Barrier(2)

        def claim(member):
            close_old_connections()
            barrier.wait()
            try:
                return ("winner", ChoreAssignment.claim(chore, member))
            except ValidationError as exc:
                return ("conflict", str(exc))
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(claim, (self.member, self.competitor)))

        self.assertEqual([result[0] for result in results].count("winner"), 1)
        self.assertEqual([result[0] for result in results].count("conflict"), 1)
        self.assertEqual(
            ChoreAssignment.objects.filter(chore=chore, is_active=True).count(),
            1,
        )

    def test_incompatible_operations_have_no_side_effects(self):
        manual = self.chore(Chore.AssignmentMode.MANUAL)
        claim = self.chore(Chore.AssignmentMode.CLAIM)
        rotation = self.chore(Chore.AssignmentMode.ROTATION)
        before = ChoreAssignment.objects.count()
        with self.assertRaises(ValidationError):
            ChoreAssignment.claim(manual, self.member)
        with self.assertRaises(ValidationError):
            ChoreAssignment.create_manual(claim, self.member)
        with self.assertRaises(ValidationError):
            ChoreAssignment.create_manual(rotation, self.member)
        self.assertEqual(ChoreAssignment.objects.count(), before)

    def test_mode_change_rejects_conflicting_active_assignment(self):
        chore = self.chore(Chore.AssignmentMode.MANUAL)
        ChoreAssignment.create_manual(chore, self.member)
        chore.assignment_mode = Chore.AssignmentMode.CLAIM
        with self.assertRaises(ValidationError):
            chore.save()
        chore.refresh_from_db()
        self.assertEqual(chore.assignment_mode, Chore.AssignmentMode.MANUAL)

    def test_rotation_members_preserve_order_and_household_boundary(self):
        chore = self.chore(Chore.AssignmentMode.ROTATION)
        rotation = RotationMember.objects.create(
            chore=chore, membership=self.member, position=1
        )
        self.assertEqual(chore.rotation_members.get(), rotation)
        with self.assertRaises(ValidationError):
            RotationMember.objects.create(
                chore=chore, membership=self.outsider, position=2
            )

    def add_rotation_member(self, chore, username, position):
        user = get_user_model().objects.create_user(username=username)
        membership = Membership.objects.create(
            household=self.household, user=user, role=Membership.Role.MEMBER
        )
        RotationMember.objects.create(
            chore=chore, membership=membership, position=position
        )
        return membership

    def test_rotation_scheduling_cycles_and_wraps(self):
        chore = self.chore(Chore.AssignmentMode.ROTATION)
        first = self.add_rotation_member(chore, "first", 1)
        second = self.add_rotation_member(chore, "second", 2)

        assignments = [
            ChoreAssignment.schedule_rotation(chore, uuid.uuid4())
            for _ in range(3)
        ]

        self.assertEqual(
            [assignment.membership_id for assignment in assignments],
            [first.id, second.id, first.id],
        )
        chore.refresh_from_db()
        self.assertEqual(chore.rotation_position, 2)


    def test_rotation_scheduling_is_idempotent_and_one_member_is_stable(self):
        chore = self.chore(Chore.AssignmentMode.ROTATION)
        member = self.add_rotation_member(chore, "only", 4)
        occurrence = uuid.uuid4()

        first = ChoreAssignment.schedule_rotation(chore, occurrence)
        second = ChoreAssignment.schedule_rotation(chore, occurrence)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ChoreAssignment.objects.filter(chore=chore).count(), 1)
        self.assertEqual(first.membership_id, member.id)
        chore.refresh_from_db()
        self.assertEqual(chore.rotation_position, 4)

    def test_rotation_skips_inactive_members_and_preserves_cursor_when_empty(self):
        chore = self.chore(Chore.AssignmentMode.ROTATION)
        inactive = self.add_rotation_member(chore, "inactive", 1)
        active = self.add_rotation_member(chore, "active", 2)
        inactive.is_active = False
        inactive.save()

        assignment = ChoreAssignment.schedule_rotation(chore, uuid.uuid4())
        self.assertEqual(assignment.membership_id, active.id)
        chore.refresh_from_db()
        self.assertEqual(chore.rotation_position, 1)

        active.is_active = False
        active.save()
        before = chore.rotation_position
        self.assertIsNone(ChoreAssignment.schedule_rotation(chore, uuid.uuid4()))
        chore.refresh_from_db()
        self.assertEqual(chore.rotation_position, before)

        active.is_active = True
        active.save()
        retry = ChoreAssignment.schedule_rotation(chore, uuid.uuid4())
        self.assertEqual(retry.membership_id, active.id)

    def test_rotation_sequence_changes_use_current_order(self):
        chore = self.chore(Chore.AssignmentMode.ROTATION)
        first = self.add_rotation_member(chore, "sequence-first", 10)
        second = self.add_rotation_member(chore, "sequence-second", 20)
        chore.rotation_position = 20
        chore.save()

        RotationMember.objects.filter(membership=first).update(position=30)
        assignment = ChoreAssignment.schedule_rotation(chore, uuid.uuid4())

        self.assertEqual(assignment.membership_id, second.id)

    def test_concurrent_rotation_scheduling_shares_one_assignment(self):
        chore = self.chore(Chore.AssignmentMode.ROTATION)
        first = self.add_rotation_member(chore, "concurrent-first", 1)
        self.add_rotation_member(chore, "concurrent-second", 2)
        occurrence = uuid.uuid4()
        barrier = threading.Barrier(2)

        def schedule():
            close_old_connections()
            barrier.wait()
            try:
                return ChoreAssignment.schedule_rotation(chore, occurrence)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            assignments = list(executor.map(lambda _: schedule(), (1, 2)))

        self.assertEqual(assignments[0].pk, assignments[1].pk)
        self.assertEqual(assignments[0].membership_id, first.id)
        self.assertEqual(
            ChoreAssignment.objects.filter(
                chore=chore, occurrence=occurrence, is_active=True
            ).count(),
            1,
        )
        chore.refresh_from_db()
        self.assertEqual(chore.rotation_position, 2)


class ChoreAPITests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.client = APIClient()
        self.household = Household.objects.create(name="API household")
        self.admin = self.user_model.objects.create_user(username="chore-admin")
        self.member_user = self.user_model.objects.create_user(username="chore-member")
        self.admin_membership = Membership.objects.create(
            household=self.household, user=self.admin, role=Membership.Role.ADMIN
        )
        self.member_membership = Membership.objects.create(
            household=self.household, user=self.member_user, role=Membership.Role.MEMBER
        )
        self.chore_url = reverse("chore-list")

    def test_admin_crud_scopes_household_and_derives_points(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            self.chore_url,
            {
                "name": "Wash dishes",
                "difficulty": "hard",
                "assignment_mode": "manual",
                "recurrence_mode": "fixed",
                "fixed_recurrence": "daily",
                "anchor_date": timezone.localdate().isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["points"], 5)
        chore_id = response.data["id"]
        response = self.client.patch(
            reverse("chore-detail", args=[chore_id]),
            {"name": "Wash the dishes"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.delete(reverse("chore-detail", args=[chore_id]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_member_queue_only_shows_assigned_and_available_claim_chores(self):
        assigned = Chore.objects.create(
            household=self.household, name="Assigned", difficulty="easy",
            assignment_mode=Chore.AssignmentMode.MANUAL,
            anchor_date=timezone.localdate(),
        )
        ChoreAssignment.create_manual(assigned, self.member_membership)
        hidden = Chore.objects.create(
            household=self.household, name="Unassigned", difficulty="easy",
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        claim = Chore.objects.create(
            household=self.household, name="Claim", difficulty="medium",
            assignment_mode=Chore.AssignmentMode.CLAIM,
            anchor_date=timezone.localdate(),
        )
        self.client.force_authenticate(self.member_user)
        response = self.client.get(reverse("my-chore-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["name"] for item in response.data["results"]], ["Assigned", "Claim"])
        self.assertNotIn(hidden.id, [item["id"] for item in response.data["results"]])
        self.assertEqual(response.data["results"][1]["due_state"], "due")

    def test_member_can_claim_due_pool_item_once(self):
        chore = Chore.objects.create(
            household=self.household, name="Take bins", difficulty="easy",
            assignment_mode=Chore.AssignmentMode.CLAIM,
            anchor_date=timezone.localdate(),
        )
        self.client.force_authenticate(self.member_user)
        url = reverse("my-chore-claim", args=[chore.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["assignee"]["membership_id"], self.member_membership.id)
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_invalid_chore_data_and_cross_household_objects_are_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            self.chore_url,
            {"name": " ", "difficulty": "easy", "assignment_mode": "manual"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        other = Household.objects.create(name="Other")
        other_admin = self.user_model.objects.create_user(username="other-admin")
        Membership.objects.create(household=other, user=other_admin, role=Membership.Role.ADMIN)
        foreign = Chore.objects.create(
            household=other, name="Foreign", difficulty="easy",
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        response = self.client.get(reverse("chore-detail", args=[foreign.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_member_queue_covers_rotation_matrix_and_filters(self):
        rotation = Chore.objects.create(
            household=self.household, name="Rotation", difficulty="easy",
            assignment_mode=Chore.AssignmentMode.ROTATION,
            recurrence_mode=Chore.RecurrenceMode.FLEXIBLE,
        )
        RotationMember.objects.create(
            chore=rotation, membership=self.member_membership, position=1
        )
        occurrence = uuid.uuid4()
        ChoreAssignment.schedule_rotation(rotation, occurrence)
        claim = Chore.objects.create(
            household=self.household, name="Pool", difficulty="medium",
            assignment_mode=Chore.AssignmentMode.CLAIM,
        )
        manual = Chore.objects.create(
            household=self.household, name="Manual", difficulty="hard",
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        ChoreAssignment.create_manual(manual, self.member_membership)
        self.client.force_authenticate(self.member_user)

        response = self.client.get(
            reverse("my-chore-list"),
            {"assignment_mode": "rotation"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["name"] for item in response.data["results"]], ["Rotation"])
        self.assertEqual(response.data["results"][0]["occurrence"], str(occurrence))

        response = self.client.get(
            reverse("my-chore-list"),
            {"recurrence_mode": "flexible"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["name"] for item in response.data["results"]], ["Rotation"])
        response = self.client.get(
            reverse("my-chore-list"), {"assignment_mode": "bogus"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("assignment_mode", response.data)
        response = self.client.get(
            reverse("my-chore-list"),
            {"assignment_mode": ["manual", "claim"]},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("assignment_mode", response.data)
        self.assertEqual(
            self.client.get(
                reverse("my-chore-list"), {"assignment_mode": "claim"}
            ).status_code,
            status.HTTP_200_OK,
        )

    def test_queue_due_states_and_pagination_edges_are_explicit(self):
        today = timezone.localdate()
        for index, anchor in enumerate((today - timedelta(days=1), today, today + timedelta(days=1))):
            chore = Chore.objects.create(
                household=self.household, name=f"Due {index}", difficulty="easy",
                assignment_mode=(
                    Chore.AssignmentMode.MANUAL
                    if index == 2 else Chore.AssignmentMode.CLAIM
                ),
                anchor_date=anchor,
            )
            if index == 2:
                ChoreAssignment.create_manual(chore, self.member_membership)
        self.client.force_authenticate(self.member_user)
        for state, name in (("overdue", "Due 0"), ("due", "Due 1"), ("upcoming", "Due 2")):
            response = self.client.get(reverse("my-chore-list"), {"due_state": state})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual([item["name"] for item in response.data["results"]], [name])
        response = self.client.get(reverse("my-chore-list"), {"page": "999"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_member_permissions_and_inactive_claim_assignment_are_safe(self):
        inactive = Chore.objects.create(
            household=self.household, name="Inactive assignment", difficulty="easy",
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        assignment = ChoreAssignment.create_manual(inactive, self.member_membership)
        assignment.is_active = False
        assignment.save(update_fields=["is_active"])
        non_member = self.user_model.objects.create_user(username="outsider")
        self.client.force_authenticate(non_member)
        response = self.client.get(reverse("my-chore-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.member_user)
        response = self.client.post(reverse("my-chore-claim", args=[inactive.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class DueSurfaceAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        user_model = get_user_model()
        self.household = Household.objects.create(name="Due surfaces")
        self.user = user_model.objects.create_user(username="due-member")
        self.membership = Membership.objects.create(
            household=self.household, user=self.user, role=Membership.Role.MEMBER
        )
        self.today = timezone.localdate()

    def chore(self, name, anchor_date, mode=Chore.AssignmentMode.MANUAL):
        chore = Chore.objects.create(
            household=self.household, name=name, difficulty=Chore.Difficulty.EASY,
            assignment_mode=mode, anchor_date=anchor_date,
        )
        assignment = None
        if mode == Chore.AssignmentMode.MANUAL:
            assignment = ChoreAssignment.create_manual(chore, self.membership)
        return chore, assignment

    def get_surface(self):
        self.client.force_authenticate(self.user)
        return self.client.get(reverse("due-overdue"))

    def test_due_overdue_future_and_empty_shape_are_separated_at_date_boundary(self):
        _, due = self.chore("Due", self.today)
        _, overdue = self.chore("Overdue", self.today - timedelta(days=1))
        self.chore("Future", self.today + timedelta(days=1))

        response = self.get_surface()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["chore"]["name"] for item in response.data["due"]], ["Due"])
        self.assertEqual(
            [item["chore"]["name"] for item in response.data["overdue"]], ["Overdue"]
        )
        self.assertEqual(response.data["due"][0]["occurrence"], str(due.occurrence))
        self.assertEqual(response.data["due"][0]["due_state"], "due")
        self.assertEqual(response.data["overdue"][0]["due_state"], "overdue")
        self.assertIn("recurrence", response.data["due"][0])
        self.assertEqual(response.data["timezone"], "UTC")

        self.household.chores.all().delete()
        response = self.get_surface()
        self.assertEqual(response.data["due"], [])
        self.assertEqual(response.data["overdue"], [])

    def test_pending_and_rejected_remain_but_approved_is_removed_read_only(self):
        pending_chore, pending_assignment = self.chore("Pending", self.today)
        rejected_chore, rejected_assignment = self.chore("Rejected", self.today)
        approved_chore, approved_assignment = self.chore("Approved", self.today)
        reviewer = Membership.objects.create(
            household=self.household,
            user=get_user_model().objects.create_user(username="due-reviewer"),
            role=Membership.Role.MEMBER,
        )
        for chore, assignment, status_value in (
            (pending_chore, pending_assignment, Completion.Status.PENDING),
            (rejected_chore, rejected_assignment, Completion.Status.REJECTED),
            (approved_chore, approved_assignment, Completion.Status.APPROVED),
        ):
            Completion.objects.create(
                household=self.household, chore=chore, assignment=assignment,
                submitted_by=self.membership, occurrence=assignment.occurrence,
                status=status_value,
                reviewer=reviewer if status_value != Completion.Status.PENDING else None,
                reviewed_at=timezone.now() if status_value != Completion.Status.PENDING else None,
            )
        before = list(ChoreAssignment.objects.values_list("is_active", flat=True))

        response = self.get_surface()

        self.assertEqual(
            {item["chore"]["name"] for item in response.data["due"]},
            {"Pending", "Rejected"},
        )
        self.assertEqual(
            list(ChoreAssignment.objects.values_list("is_active", flat=True)), before
        )

    def test_claim_pool_is_visible_only_when_available_and_other_household_is_hidden(self):
        claim, _ = self.chore("Claim", self.today, Chore.AssignmentMode.CLAIM)
        unavailable, _ = self.chore("Unavailable", self.today, Chore.AssignmentMode.CLAIM)
        unavailable_user = get_user_model().objects.create_user(username="busy-member")
        unavailable_member = Membership.objects.create(
            household=self.household, user=unavailable_user, role=Membership.Role.MEMBER
        )
        other_household = Household.objects.create(name="Other")
        other_user = get_user_model().objects.create_user(username="other-member")
        other_member = Membership.objects.create(
            household=other_household, user=other_user, role=Membership.Role.MEMBER
        )
        other_chore = Chore.objects.create(
            household=other_household, name="Foreign", difficulty="easy",
            assignment_mode=Chore.AssignmentMode.MANUAL, anchor_date=self.today,
        )
        ChoreAssignment.create_manual(other_chore, other_member)
        ChoreAssignment.claim(unavailable, unavailable_member)

        response = self.get_surface()

        self.assertEqual([item["chore"]["name"] for item in response.data["due"]], ["Claim"])
        self.assertTrue(response.data["due"][0]["claimable"])
        self.assertIsNone(response.data["due"][0]["occurrence"])

    def test_authentication_and_active_membership_are_required(self):
        response = self.client.get(reverse("due-overdue"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.force_authenticate(self.user)
        self.membership.is_active = False
        self.membership.save(update_fields=["is_active"])
        response = self.client.get(reverse("due-overdue"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(TIME_ZONE="America/Los_Angeles")
    @patch("chores.views.timezone.now")
    def test_api_uses_project_timezone_at_dst_local_midnight(self, mocked_now):
        mocked_now.return_value = datetime.fromisoformat("2026-03-08T08:00:00+00:00")
        _, assignment = self.chore("Spring transition", date(2026, 3, 8))

        response = self.get_surface()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = response.data["due"][0]
        self.assertEqual(item["due_date"], "2026-03-08")
        self.assertEqual(item["due_at"], "2026-03-08T00:00:00-08:00")
        self.assertEqual(item["occurrence"], str(assignment.occurrence))
        mocked_now.return_value = datetime.fromisoformat("2026-11-01T07:00:00+00:00")
        self.chore("Fall transition", date(2026, 11, 1))

        response = self.get_surface()

        fall_item = next(
            item for item in response.data["due"]
            if item["chore"]["name"] == "Fall transition"
        )
        self.assertEqual(fall_item["due_at"], "2026-11-01T00:00:00-07:00")

    def test_approved_completion_uses_recurrence_next_occurrence(self):
        chore, first_assignment = self.chore("Daily recurrence", self.today)
        chore.fixed_recurrence = Chore.FixedRecurrence.DAILY
        chore.save()
        completion = Completion.objects.create(
            household=self.household, chore=chore, assignment=first_assignment,
            submitted_by=self.membership, occurrence=first_assignment.occurrence,
            status=Completion.Status.APPROVED,
            reviewer=self.membership,
            reviewed_at=timezone.now(),
        )
        Completion.objects.filter(pk=completion.pk).update(
            submitted_at=timezone.now() - timedelta(days=1)
        )
        next_assignment = ChoreAssignment.create_manual(
            chore, self.membership, occurrence=uuid.uuid4()
        )

        response = self.get_surface()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [(item["chore"]["name"], item["occurrence"]) for item in response.data["due"]],
            [("Daily recurrence", str(next_assignment.occurrence))],
        )
        self.assertEqual(response.data["due"][0]["due_date"], str(self.today))

    def test_rejected_completion_has_no_gamification_or_assignment_side_effects(self):
        chore, assignment = self.chore("Rejected work", self.today)
        reviewer = Membership.objects.create(
            household=self.household,
            user=get_user_model().objects.create_user(username="reject-reviewer"),
            role=Membership.Role.MEMBER,
        )
        completion = Completion.objects.create(
            household=self.household, chore=chore, assignment=assignment,
            submitted_by=self.membership, occurrence=assignment.occurrence,
            status=Completion.Status.REJECTED, reviewer=reviewer,
            reviewed_at=timezone.now(),
        )
        before = {
            "assignment": assignment.is_active,
            "points": PointsLedger.objects.count(),
            "streaks": MemberStreak.objects.count(),
            "badges": BadgeAward.objects.count(),
            "completion_status": completion.status,
        }

        response = self.get_surface()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["due"][0]["occurrence"], str(assignment.occurrence))
        assignment.refresh_from_db()
        completion.refresh_from_db()
        self.assertEqual(assignment.is_active, before["assignment"])
        self.assertEqual(PointsLedger.objects.count(), before["points"])
        self.assertEqual(MemberStreak.objects.count(), before["streaks"])
        self.assertEqual(BadgeAward.objects.count(), before["badges"])
        self.assertEqual(completion.status, before["completion_status"])

    def test_inactive_assignee_and_future_claim_are_hidden(self):
        inactive_user = get_user_model().objects.create_user(username="inactive-assignee")
        inactive = Membership.objects.create(
            household=self.household, user=inactive_user, role=Membership.Role.MEMBER,
        )
        inactive_chore = Chore.objects.create(
            household=self.household, name="Inactive", difficulty=Chore.Difficulty.EASY,
            assignment_mode=Chore.AssignmentMode.MANUAL, anchor_date=self.today,
        )
        ChoreAssignment.create_manual(inactive_chore, inactive)
        Membership.objects.filter(pk=inactive.pk).update(is_active=False)
        self.chore("Future claim", self.today + timedelta(days=1), Chore.AssignmentMode.CLAIM)

        response = self.get_surface()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["due"], [])
        self.assertEqual(response.data["overdue"], [])

    def test_identifiers_and_unknown_filters_do_not_bypass_household_scope(self):
        chore, _ = self.chore("Visible", self.today)
        other_household = Household.objects.create(name="Other due household")
        other_user = get_user_model().objects.create_user(username="other-due-member")
        other_member = Membership.objects.create(
            household=other_household, user=other_user, role=Membership.Role.MEMBER
        )
        other_chore = Chore.objects.create(
            household=other_household, name="Secret", difficulty=Chore.Difficulty.EASY,
            assignment_mode=Chore.AssignmentMode.MANUAL, anchor_date=self.today,
        )
        other_assignment = ChoreAssignment.create_manual(other_chore, other_member)

        self.client.force_authenticate(self.user)
        response = self.client.get(
            reverse("due-overdue"),
            {
                "chore_id": other_chore.pk,
                "occurrence": str(other_assignment.occurrence),
                "unknown": "not-a-real-filter",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["chore"]["id"] for item in response.data["due"]], [chore.pk]
        )
        self.assertNotContains(response, "Secret")

    @patch("django.core.mail.send_mail")
    def test_read_only_surface_has_no_external_notification_side_effect(self, send_mail):
        self.chore("Read only", self.today)
        before = {
            "chores": list(Chore.objects.values_list("id", "updated_at")),
            "assignments": list(ChoreAssignment.objects.values_list("id", "is_active")),
            "completions": Completion.objects.count(),
        }

        response = self.get_surface()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        send_mail.assert_not_called()
        self.assertEqual(
            list(Chore.objects.values_list("id", "updated_at")), before["chores"]
        )
        self.assertEqual(
            list(ChoreAssignment.objects.values_list("id", "is_active")),
            before["assignments"],
        )
        self.assertEqual(Completion.objects.count(), before["completions"])


class CompletionAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        user_model = get_user_model()
        self.household = Household.objects.create(name="Completions")
        self.submitter = user_model.objects.create_user(username="submitter")
        self.reviewer = user_model.objects.create_user(username="reviewer")
        self.submitter_membership = Membership.objects.create(
            household=self.household, user=self.submitter, role=Membership.Role.MEMBER
        )
        self.reviewer_membership = Membership.objects.create(
            household=self.household, user=self.reviewer, role=Membership.Role.MEMBER
        )
        self.chore = Chore.objects.create(
            household=self.household, name="Clean", difficulty="easy",
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        self.assignment = ChoreAssignment.create_manual(self.chore, self.submitter_membership)

    def test_submit_pending_and_duplicate_is_rejected(self):
        self.client.force_authenticate(self.submitter)
        url = reverse("my-chore-complete", args=[self.chore.pk])
        response = self.client.post(url, {"occurrence": str(self.assignment.occurrence)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], Completion.Status.PENDING)
        self.assertEqual(Completion.objects.count(), 1)
        response = self.client.post(url, {"occurrence": str(self.assignment.occurrence)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Completion.objects.count(), 1)

    def test_pending_completion_can_be_retrieved(self):
        completion = Completion.submit(
            membership=self.submitter_membership, chore=self.chore,
            occurrence=self.assignment.occurrence,
        )
        self.client.force_authenticate(self.reviewer)
        response = self.client.get(reverse("completion-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["id"], completion.id)
        response = self.client.get(reverse("completion-detail", args=[completion.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Completion.Status.PENDING)

    def test_reviewer_can_approve_and_self_review_is_denied(self):
        completion = Completion.submit(
            membership=self.submitter_membership, chore=self.chore,
            occurrence=self.assignment.occurrence,
        )
        self.client.force_authenticate(self.submitter)
        response = self.client.post(
            reverse("completion-review", args=[completion.pk]),
            {"status": Completion.Status.APPROVED}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.client.force_authenticate(self.reviewer)
        response = self.client.post(
            reverse("completion-review", args=[completion.pk]),
            {"status": Completion.Status.APPROVED}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        completion.refresh_from_db()
        self.assertEqual(completion.status, Completion.Status.APPROVED)
        self.assertFalse(self.assignment.__class__.objects.get(pk=self.assignment.pk).is_active)
        response = self.client.post(
            reverse("completion-review", args=[completion.pk]),
            {"status": Completion.Status.REJECTED}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejection_preserves_history_and_assignment_but_blocks_retry(self):
        completion = Completion.submit(
            membership=self.submitter_membership, chore=self.chore,
            occurrence=self.assignment.occurrence,
        )
        self.client.force_authenticate(self.reviewer)
        response = self.client.post(
            reverse("completion-review", args=[completion.pk]),
            {"status": Completion.Status.REJECTED}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        completion.refresh_from_db()
        self.assignment.refresh_from_db()
        self.assertEqual(completion.status, Completion.Status.REJECTED)
        self.assertEqual(completion.reviewer_id, self.reviewer_membership.id)
        self.assertIsNotNone(completion.reviewed_at)
        self.assertTrue(self.assignment.is_active)
        self.client.force_authenticate(self.submitter)
        response = self.client.post(
            reverse("my-chore-complete", args=[self.chore.pk]),
            {"occurrence": str(self.assignment.occurrence)}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Completion.objects.count(), 1)

    def test_invalid_unknown_ineligible_and_inactive_submissions_do_not_write(self):
        self.client.force_authenticate(self.submitter)
        before = Completion.objects.count()
        for payload in ({}, {"occurrence": str(uuid.uuid4())}, {"occurrence": "bad"}):
            response = self.client.post(
                reverse("my-chore-complete", args=[self.chore.pk]),
                payload, format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Completion.objects.count(), before)

        self.client.force_authenticate(self.reviewer)
        response = self.client.post(
            reverse("my-chore-complete", args=[self.chore.pk]),
            {"occurrence": str(self.assignment.occurrence)}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assignment.is_active = False
        self.assignment.save(update_fields=["is_active"])
        self.client.force_authenticate(self.submitter)
        response = self.client.post(
            reverse("my-chore-complete", args=[self.chore.pk]),
            {"occurrence": str(self.assignment.occurrence)}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Completion.objects.count(), before)

    def test_cross_household_completion_is_not_retrievable_or_reviewable(self):
        other = Household.objects.create(name="Other")
        user = get_user_model().objects.create_user(username="other")
        member = Membership.objects.create(
            household=other, user=user, role=Membership.Role.MEMBER
        )
        chore = Chore.objects.create(
            household=other, name="Other chore", difficulty="easy",
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        assignment = ChoreAssignment.create_manual(chore, member)
        completion = Completion.submit(
            membership=member, chore=chore, occurrence=assignment.occurrence
        )
        self.client.force_authenticate(self.reviewer)
        self.assertEqual(
            self.client.get(reverse("completion-detail", args=[completion.pk])).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.post(
                reverse("completion-review", args=[completion.pk]),
                {"status": Completion.Status.APPROVED}, format="json",
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        completion.refresh_from_db()
        self.assertEqual(completion.status, Completion.Status.PENDING)

    def test_unauthenticated_review_is_rejected(self):
        completion = Completion.submit(
            membership=self.submitter_membership, chore=self.chore,
            occurrence=self.assignment.occurrence,
        )
        response = self.client.post(
            reverse("completion-review", args=[completion.pk]),
            {"status": Completion.Status.APPROVED}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_review_and_replay_leave_state_unchanged(self):
        completion = Completion.submit(
            membership=self.submitter_membership, chore=self.chore,
            occurrence=self.assignment.occurrence,
        )
        self.client.force_authenticate(self.reviewer)
        response = self.client.post(
            reverse("completion-review", args=[completion.pk]),
            {"status": "pending"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(
            reverse("completion-review", args=[completion.pk]),
            {"status": Completion.Status.APPROVED}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        completion.refresh_from_db()
        reviewed_at = completion.reviewed_at
        response = self.client.post(
            reverse("completion-review", args=[completion.pk]),
            {"status": Completion.Status.REJECTED}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        completion.refresh_from_db()
        self.assertEqual(completion.status, Completion.Status.APPROVED)
        self.assertEqual(completion.reviewed_at, reviewed_at)

    def test_cross_household_and_inactive_members_are_denied(self):
        self.client.force_authenticate(self.submitter)
        other = Household.objects.create(name="Other")
        other_user = get_user_model().objects.create_user(username="outsider")
        Membership.objects.create(household=other, user=other_user, role=Membership.Role.MEMBER)
        self.submitter_membership.is_active = False
        self.submitter_membership.save(update_fields=["is_active"])
        response = self.client.post(
            reverse("my-chore-complete", args=[self.chore.pk]),
            {"occurrence": str(self.assignment.occurrence)}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CompletionReviewRaceTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        user_model = get_user_model()
        self.household = Household.objects.create(name="Race household")
        submitter = user_model.objects.create_user(username="race-submitter")
        reviewer = user_model.objects.create_user(username="race-reviewer")
        self.submitter_membership = Membership.objects.create(
            household=self.household, user=submitter, role=Membership.Role.MEMBER
        )
        self.reviewer_membership = Membership.objects.create(
            household=self.household, user=reviewer, role=Membership.Role.MEMBER
        )
        chore = Chore.objects.create(
            household=self.household, name="Race chore", difficulty="easy",
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        assignment = ChoreAssignment.create_manual(chore, self.submitter_membership)
        self.completion = Completion.submit(
            membership=self.submitter_membership, chore=chore,
            occurrence=assignment.occurrence,
        )

    def test_concurrent_reviews_have_one_winner_and_one_final_state(self):
        barrier = threading.Barrier(2)

        def review():
            close_old_connections()
            try:
                barrier.wait()
                Completion.review(
                    completion_id=self.completion.pk,
                    reviewer=self.reviewer_membership,
                    status=Completion.Status.APPROVED,
                )
                return "won"
            except (ValidationError, OperationalError):
                return "lost"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: review(), (1, 2)))
        self.assertEqual(outcomes.count("won"), 1)
        self.completion.refresh_from_db()
        self.assertEqual(self.completion.status, Completion.Status.APPROVED)
        self.assertEqual(
            Completion.objects.filter(
                pk=self.completion.pk, status=Completion.Status.APPROVED
            ).count(),
            1,
        )


class BadgeAwardTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.household = Household.objects.create(name="Badge household")
        self.member = Membership.objects.create(
            household=self.household,
            user=user_model.objects.create_user(username="badge-member"),
            role=Membership.Role.MEMBER,
        )
        self.reviewer = Membership.objects.create(
            household=self.household,
            user=user_model.objects.create_user(username="badge-reviewer"),
            role=Membership.Role.MEMBER,
        )
        self.chore = Chore.objects.create(
            household=self.household, name="Badge chore",
            difficulty=Chore.Difficulty.HARD,
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )

    def make_completion(self, occurrence=None, status=Completion.Status.APPROVED):
        assignment = ChoreAssignment.create_manual(self.chore, self.member)
        completion = Completion.submit(
            membership=self.member, chore=self.chore, occurrence=assignment.occurrence
        )
        if status != Completion.Status.PENDING:
            Completion.objects.filter(pk=completion.pk).update(
                status=status, reviewer=self.reviewer, reviewed_at=timezone.now()
            )
            completion.refresh_from_db()
        return completion

    def test_catalog_is_exactly_three_fixed_badges(self):
        self.assertEqual(
            [badge["identifier"] for badge in BadgeCatalog.ALL],
            ["seven_day_streak", "hundred_points", "fifty_completions"],
        )
        for badge in BadgeCatalog.ALL:
            self.assertIsInstance(badge["threshold"], int)
            self.assertTrue({"display_name", "description", "metric"} <= badge.keys())

    def test_threshold_award_is_durable_and_idempotent(self):
        completion = self.make_completion()
        PointsLedger.award_for_completion(completion)
        streak = MemberStreak.objects.get(membership=self.member)
        streak.current_streak = 7
        streak.save(update_fields=["current_streak", "updated_at"])
        awards = BadgeAward.evaluate_for_completion(completion)
        self.assertEqual(len(awards), 1)
        self.assertEqual(awards[0].badge_identifier, "seven_day_streak")
        self.assertEqual(
            len(BadgeAward.evaluate_for_completion(completion)), 1
        )
        awards[0].refresh_from_db()
        awarded_at = awards[0].awarded_at
        self.assertEqual(awards[0].awarded_at, awarded_at)

    def test_pending_and_rejected_completions_do_not_earn_badges(self):
        pending = self.make_completion(status=Completion.Status.PENDING)
        with self.assertRaises(ValidationError):
            BadgeAward.evaluate_for_completion(pending)
        rejected = self.make_completion(status=Completion.Status.REJECTED)
        with self.assertRaises(ValidationError):
            BadgeAward.evaluate_for_completion(rejected)
        self.assertFalse(BadgeAward.objects.exists())

    def approved_completion(self, member=None, chore=None, submitted_at=None):
        member = member or self.member
        chore = chore or self.chore
        assignment = ChoreAssignment.create_manual(chore, member)
        completion = Completion.objects.create(
            household=member.household,
            chore=chore,
            assignment=assignment,
            submitted_by=member,
            occurrence=assignment.occurrence,
            status=Completion.Status.APPROVED,
            reviewer=self.reviewer,
            reviewed_at=timezone.now(),
        )
        if submitted_at is not None:
            Completion.objects.filter(pk=completion.pk).update(submitted_at=submitted_at)
            completion.refresh_from_db()
        return completion

    def test_every_badge_has_below_exact_and_above_threshold_coverage(self):
        for badge in BadgeCatalog.ALL:
            with self.subTest(badge=badge["identifier"]):
                member = Membership.objects.create(
                    household=self.household,
                    user=get_user_model().objects.create_user(
                        username=f"threshold-{badge['identifier']}"
                    ),
                    role=Membership.Role.MEMBER,
                )
                chore = Chore.objects.create(
                    household=self.household,
                    name=f"Threshold {badge['identifier']}",
                    difficulty=Chore.Difficulty.EASY,
                    assignment_mode=Chore.AssignmentMode.MANUAL,
                )
                completion = self.approved_completion(member, chore)
                if badge["metric"] == "current_streak":
                    values = (6, 7, 8)
                    for value in values:
                        streak = MemberStreak.objects.get(membership=member)
                        streak.current_streak = value
                        streak.save(update_fields=["current_streak", "updated_at"])
                        awards = BadgeAward.evaluate_for_completion(completion)
                        self.assertEqual(
                            any(a.badge_identifier == badge["identifier"] for a in awards),
                            value >= badge["threshold"],
                        )
                else:
                    target = badge["threshold"]
                    if badge["metric"] == "approved_points":
                        PointsLedger.award_for_completion(completion)
                    else:
                        for approved in Completion.objects.filter(
                            submitted_by=member, status=Completion.Status.APPROVED
                        ):
                            PointsLedger.award_for_completion(approved)
                    metric_values = (
                        (target - 1, target, target + 1)
                        if badge["metric"] == "approved_completions"
                        else (99, 100, 101)
                    )
                    for value in metric_values:
                        if badge["metric"] == "approved_completions":
                            # Add or remove only test data for this isolated member.
                            current = Completion.objects.filter(
                                submitted_by=member, status=Completion.Status.APPROVED
                            ).count()
                            while current < value:
                                self.approved_completion(member, chore)
                                current += 1
                        else:
                            current = PointsLedger.total_for_member(member)
                            while current < value:
                                extra = self.approved_completion(member, chore)
                                PointsLedger.award_for_completion(extra)
                                current += chore.points
                        awards = BadgeAward.evaluate_for_completion(completion)
                        self.assertEqual(
                            any(a.badge_identifier == badge["identifier"] for a in awards),
                            value >= target,
                        )

    def test_streak_gap_requires_seven_new_consecutive_days(self):
        for offset in range(6):
            MemberStreak.record_approved_completion(
                self.approved_completion(
                    submitted_at=timezone.make_aware(
                        datetime(2026, 5, 1 + offset)
                    )
                )
            )
        self.assertFalse(
            BadgeAward.objects.filter(
                member=self.member, badge_identifier="seven_day_streak"
            ).exists()
        )
        completion = self.approved_completion(
            submitted_at=timezone.make_aware(datetime(2026, 5, 8))
        )
        MemberStreak.record_approved_completion(completion)
        BadgeAward.evaluate_for_completion(completion)
        self.assertFalse(
            BadgeAward.objects.filter(
                member=self.member, badge_identifier="seven_day_streak"
            ).exists()
        )
        for offset in range(1, 7):
            completion = self.approved_completion(
                submitted_at=timezone.make_aware(datetime(2026, 5, 8 + offset))
            )
            MemberStreak.record_approved_completion(completion)
        BadgeAward.evaluate_for_completion(completion)
        self.assertTrue(
            BadgeAward.objects.filter(
                member=self.member, badge_identifier="seven_day_streak"
            ).exists()
        )

    def test_successful_approval_directly_awards_badge(self):
        for offset in range(6):
            MemberActivityDay.objects.create(
                membership=self.member,
                household=self.household,
                activity_date=date(2026, 6, 1 + offset),
            )
        streak = MemberStreak.objects.get(membership=self.member)
        streak.current_streak = 6
        streak.save(update_fields=["current_streak", "updated_at"])
        assignment = ChoreAssignment.create_manual(self.chore, self.member)
        completion = Completion.submit(
            membership=self.member, chore=self.chore, occurrence=assignment.occurrence
        )
        Completion.objects.filter(pk=completion.pk).update(
            submitted_at=timezone.make_aware(datetime(2026, 6, 7))
        )
        Completion.review(
            completion_id=completion.pk,
            reviewer=self.reviewer,
            status=Completion.Status.APPROVED,
        )
        self.assertTrue(
            BadgeAward.objects.filter(
                member=self.member, badge_identifier="seven_day_streak"
            ).exists()
        )

    def test_badge_identifiers_are_stable_and_awards_are_not_revoked(self):
        completion = self.make_completion()
        PointsLedger.award_for_completion(completion)
        MemberStreak.objects.filter(membership=self.member).update(
            current_streak=7, best_streak=7
        )
        award = BadgeAward.evaluate_for_completion(completion)[0]
        self.assertEqual(
            {badge["identifier"] for badge in BadgeCatalog.ALL},
            {"seven_day_streak", "hundred_points", "fifty_completions"},
        )
        award.badge_identifier = "renamed_badge"
        with self.assertRaises(ValidationError):
            award.save()
        MemberActivityDay.objects.filter(membership=self.member).delete()
        Completion.objects.filter(pk=completion.pk).update(status=Completion.Status.REJECTED)
        self.assertTrue(BadgeAward.objects.filter(pk=award.pk).exists())
        self.assertEqual(
            BadgeAward.objects.get(pk=award.pk).badge_identifier, "seven_day_streak"
        )

    def test_cross_household_evaluation_cannot_award_local_member(self):
        other_household = Household.objects.create(name="Other badge household")
        other_member = Membership.objects.create(
            household=other_household,
            user=get_user_model().objects.create_user(username="other-badge-member"),
            role=Membership.Role.MEMBER,
        )
        other_chore = Chore.objects.create(
            household=other_household,
            name="Other badge chore",
            difficulty=Chore.Difficulty.EASY,
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        completion = self.approved_completion(other_member, other_chore)
        Completion.objects.filter(pk=completion.pk).update(household=self.household.pk)
        completion.refresh_from_db()
        with self.assertRaises(ValidationError):
            BadgeAward.evaluate_for_completion(completion)
        self.assertFalse(BadgeAward.objects.exists())


class BadgeAwardConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        user_model = get_user_model()
        self.household = Household.objects.create(name="Concurrent badge household")
        self.member = Membership.objects.create(
            household=self.household,
            user=user_model.objects.create_user(username="concurrent-badge-member"),
            role=Membership.Role.MEMBER,
        )
        self.reviewer = Membership.objects.create(
            household=self.household,
            user=user_model.objects.create_user(username="concurrent-badge-reviewer"),
            role=Membership.Role.MEMBER,
        )
        self.chore = Chore.objects.create(
            household=self.household,
            name="Concurrent badge chore",
            difficulty=Chore.Difficulty.HARD,
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        assignment = ChoreAssignment.create_manual(self.chore, self.member)
        self.completion = Completion.objects.create(
            household=self.household, chore=self.chore, assignment=assignment,
            submitted_by=self.member, occurrence=assignment.occurrence,
            status=Completion.Status.APPROVED, reviewer=self.reviewer,
            reviewed_at=timezone.now(),
        )
        PointsLedger.award_for_completion(self.completion)
        MemberStreak.objects.filter(membership=self.member).update(current_streak=7)

    def test_concurrent_evaluations_store_one_award(self):
        barrier = threading.Barrier(2)

        def evaluate():
            close_old_connections()
            try:
                barrier.wait()
                return BadgeAward.evaluate_for_completion(self.completion.pk)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: evaluate(), (1, 2)))
        self.assertEqual(
            {awards[0].pk for awards in results},
            {BadgeAward.objects.get(member=self.member, badge_identifier="seven_day_streak").pk},
        )
        self.assertEqual(
            BadgeAward.objects.filter(
                member=self.member, badge_identifier="seven_day_streak"
            ).count(),
            1,
        )


class ProtectedResourceView(APIView):
    def get(self, request):
        return Response({"username": request.user.username})


urlpatterns = [
    path("api/auth/token/", obtain_auth_token, name="api-token-auth"),
    path("protected/", ProtectedResourceView.as_view()),
]


@override_settings(ROOT_URLCONF="chores.tests")
class TokenAuthenticationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            username="api-user",
            password="correct-horse-battery-staple",
        )
        self.token_url = reverse("api-token-auth")
        self.protected_url = "/protected/"

    def test_valid_credentials_issue_a_token(self):
        response = self.client.post(
            self.token_url,
            {"username": "api-user", "password": "correct-horse-battery-staple"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["token"], Token.objects.get(user=self.user).key)

    def test_repeated_issuance_reuses_existing_token(self):
        token = Token.objects.create(user=self.user)

        response = self.client.post(
            self.token_url,
            {"username": "api-user", "password": "correct-horse-battery-staple"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"token": token.key})
        self.assertEqual(Token.objects.filter(user=self.user).count(), 1)

    def test_valid_token_authenticates_protected_request(self):
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.get(self.protected_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"username": "api-user"})

    def test_missing_authorization_is_rejected(self):
        response = self.client.get(self.protected_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            response.data,
            {"detail": "Authentication credentials were not provided."},
        )

    def test_malformed_unknown_and_deleted_tokens_are_rejected(self):
        response = self.client.get(
            self.protected_url,
            HTTP_AUTHORIZATION="Bearer not-a-token",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.get(
            self.protected_url,
            HTTP_AUTHORIZATION="Token not-a-token",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data, {"detail": "Invalid token."})

        token = Token.objects.create(user=self.user)
        token.delete()
        response = self.client.get(
            self.protected_url,
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data, {"detail": "Invalid token."})

    def test_invalid_credentials_do_not_reveal_username_existence(self):
        response = self.client.post(
            self.token_url,
            {"username": "api-user", "password": "wrong-password"},
            format="json",
        )
        unknown_response = self.client.post(
            self.token_url,
            {"username": "unknown-user", "password": "wrong-password"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, unknown_response.data)
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_token_endpoint_does_not_sign_up_or_mutate_household_data(self):
        user_count = self.user_model.objects.count()
        household_count = Household.objects.count()
        membership_count = Membership.objects.count()

        response = self.client.post(
            self.token_url,
            {"username": "new-user", "password": "new-user-password"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(self.user_model.objects.filter(username="new-user").exists())
        self.assertEqual(self.user_model.objects.count(), user_count)
        self.assertEqual(Household.objects.count(), household_count)
        self.assertEqual(Membership.objects.count(), membership_count)

    def test_token_authentication_is_available_without_membership(self):
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.get(self.protected_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_authentication_and_permission_defaults_are_centralized(self):
        from django.conf import settings

        self.assertEqual(
            settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"],
            ["rest_framework.authentication.TokenAuthentication"],
        )
        self.assertEqual(
            settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"],
            ["rest_framework.permissions.IsAuthenticated"],
        )



class MemberStreakTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.household = Household.objects.create(name="Streak household")
        self.user = user_model.objects.create_user(username="streak-member")
        self.member = Membership.objects.create(
            household=self.household, user=self.user, role=Membership.Role.MEMBER
        )
        self.chore = Chore.objects.create(
            household=self.household, name="Streak chore", difficulty="easy",
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )

    def completion(self, submitted_at, status=Completion.Status.APPROVED, **kwargs):
        assignment = ChoreAssignment.create_manual(self.chore, self.member)
        completion = Completion.objects.create(
            household=self.household, chore=self.chore, assignment=assignment,
            submitted_by=self.member, occurrence=assignment.occurrence, status=status,
            reviewer=self.member if status != Completion.Status.PENDING else None,
            reviewed_at=submitted_at if status != Completion.Status.PENDING else None,
            **kwargs,
        )
        Completion.objects.filter(pk=completion.pk).update(submitted_at=submitted_at)
        return Completion.objects.get(pk=completion.pk)

    def test_no_activity_starts_at_zero(self):
        streak = MemberStreak.objects.get(membership=self.member)
        self.assertEqual((streak.current_streak, streak.best_streak, streak.last_activity_date), (0, 0, None))

    def test_consecutive_and_gapped_days_preserve_best(self):
        for day in (date(2026, 4, 1), date(2026, 4, 2), date(2026, 4, 5)):
            MemberStreak.record_approved_completion(
                self.completion(timezone.make_aware(datetime.combine(day, datetime.min.time())))
            )
        streak = MemberStreak.objects.get(membership=self.member)
        self.assertEqual(streak.current_streak, 1)
        self.assertEqual(streak.best_streak, 2)
        self.assertEqual(streak.last_activity_date, date(2026, 4, 5))

    def test_same_day_duplicates_and_out_of_order_are_idempotent(self):
        first = self.completion(timezone.make_aware(datetime(2026, 4, 3, 1)))
        third = self.completion(timezone.make_aware(datetime(2026, 4, 5, 1)))
        second = self.completion(timezone.make_aware(datetime(2026, 4, 4, 1)))
        for completion in (third, first, second, first):
            MemberStreak.record_approved_completion(completion)
        self.assertEqual(MemberActivityDay.objects.filter(membership=self.member).count(), 3)
        streak = MemberStreak.objects.get(membership=self.member)
        self.assertEqual((streak.current_streak, streak.best_streak), (3, 3))

    def test_pending_rejected_and_invalid_completions_have_no_effect(self):
        pending = self.completion(timezone.now(), status=Completion.Status.PENDING)
        rejected = self.completion(timezone.now(), status=Completion.Status.REJECTED)
        for completion in (pending, rejected):
            with self.assertRaises(ValidationError):
                MemberStreak.record_approved_completion(completion)
        self.assertFalse(MemberActivityDay.objects.exists())

        with self.assertRaises(ValidationError):
            MemberStreak.activity_date_for(None)
        self.assertFalse(MemberActivityDay.objects.exists())

    def test_cross_household_completion_cannot_write_this_members_streak(self):
        other_household = Household.objects.create(name="Other streak household")
        other_member = Membership.objects.create(
            household=other_household,
            user=get_user_model().objects.create_user(username="other-streak-member"),
            role=Membership.Role.MEMBER,
        )
        other_chore = Chore.objects.create(
            household=other_household,
            name="Other streak chore",
            difficulty=Chore.Difficulty.EASY,
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        other_assignment = ChoreAssignment.create_manual(other_chore, other_member)
        other_completion = Completion.objects.create(
            household=other_household,
            chore=other_chore,
            assignment=other_assignment,
            submitted_by=other_member,
            occurrence=other_assignment.occurrence,
            status=Completion.Status.APPROVED,
            reviewer=self.member,
            reviewed_at=timezone.now(),
        )
        Completion.objects.filter(pk=other_completion.pk).update(
            submitted_at=timezone.make_aware(datetime(2026, 4, 1))
        )
        other_completion.refresh_from_db()

        MemberStreak.record_approved_completion(other_completion)

        self.assertFalse(
            MemberActivityDay.objects.filter(membership=self.member).exists()
        )
        self.assertEqual(
            MemberActivityDay.objects.filter(membership=other_member).count(), 1
        )
        with self.assertRaises(ValidationError):
            invalid = self.completion(timezone.now())
            Completion.objects.filter(pk=invalid.pk).update(
                household=other_household.pk
            )
            invalid.refresh_from_db()
            MemberStreak.record_approved_completion(invalid)

    def test_explicit_single_and_multi_day_gaps_reset_current_streak(self):
        for day in (date(2026, 4, 1), date(2026, 4, 2), date(2026, 4, 4), date(2026, 4, 7)):
            MemberStreak.record_approved_completion(
                self.completion(
                    timezone.make_aware(datetime.combine(day, datetime.min.time()))
                )
            )

        streak = MemberStreak.objects.get(membership=self.member)
        self.assertEqual(streak.current_streak, 1)
        self.assertEqual(streak.best_streak, 2)
        self.assertEqual(streak.last_activity_date, date(2026, 4, 7))

    def test_transaction_failure_rolls_back_activity_day_and_streak_update(self):
        completion = self.completion(timezone.make_aware(datetime(2026, 4, 1)))
        original_save = MemberStreak.save

        def fail_save(instance, *args, **kwargs):
            raise IntegrityError("forced activity persistence failure")

        MemberStreak.save = fail_save
        try:
            with self.assertRaises(IntegrityError):
                MemberStreak.record_approved_completion(completion)
        finally:
            MemberStreak.save = original_save

        self.assertFalse(MemberActivityDay.objects.exists())
        streak = MemberStreak.objects.get(membership=self.member)
        self.assertEqual(
            (streak.current_streak, streak.best_streak, streak.last_activity_date),
            (0, 0, None),
        )

    @override_settings(TIME_ZONE="America/Los_Angeles")
    def test_activity_date_uses_project_timezone_across_midnight_and_dst(self):
        before_midnight = self.completion(datetime.fromisoformat("2026-03-08T07:30:00+00:00"))
        after_midnight = self.completion(datetime.fromisoformat("2026-03-08T08:30:00+00:00"))
        MemberStreak.record_approved_completion(before_midnight)
        MemberStreak.record_approved_completion(after_midnight)
        self.assertEqual(
            list(MemberActivityDay.objects.values_list("activity_date", flat=True)),
            [date(2026, 3, 7), date(2026, 3, 8)],
        )

    @override_settings(TIME_ZONE="America/Los_Angeles")
    def test_activity_date_is_stable_for_both_sides_of_dst_fall_back(self):
        first = self.completion(datetime.fromisoformat("2026-11-01T08:30:00+00:00"))
        second = self.completion(datetime.fromisoformat("2026-11-01T09:30:00+00:00"))
        MemberStreak.record_approved_completion(first)
        MemberStreak.record_approved_completion(second)

        self.assertEqual(
            list(
                MemberActivityDay.objects.filter(membership=self.member).values_list(
                    "activity_date", flat=True
                )
            ),
            [date(2026, 11, 1)],
        )
        streak = MemberStreak.objects.get(membership=self.member)
        self.assertEqual((streak.current_streak, streak.best_streak), (1, 1))


class MemberStreakConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        user_model = get_user_model()
        self.household = Household.objects.create(name="Concurrent streak household")
        self.member = Membership.objects.create(
            household=self.household,
            user=user_model.objects.create_user(username="concurrent-streak-member"),
            role=Membership.Role.MEMBER,
        )
        self.chore = Chore.objects.create(
            household=self.household,
            name="Concurrent streak chore",
            difficulty=Chore.Difficulty.EASY,
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        assignment = ChoreAssignment.create_manual(
            self.chore, self.member, occurrence=uuid.uuid4()
        )
        self.completion = Completion.objects.create(
            household=self.household,
            chore=self.chore,
            assignment=assignment,
            submitted_by=self.member,
            occurrence=assignment.occurrence,
            status=Completion.Status.APPROVED,
            reviewer=self.member,
            reviewed_at=timezone.now(),
        )
        Completion.objects.filter(pk=self.completion.pk).update(
            submitted_at=timezone.make_aware(datetime(2026, 4, 1))
        )

    def test_concurrent_recording_is_idempotent(self):
        barrier = threading.Barrier(2)

        def record():
            close_old_connections()
            try:
                barrier.wait()
                return MemberStreak.record_approved_completion(self.completion.pk)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            streaks = list(executor.map(lambda _: record(), (1, 2)))

        self.assertEqual(streaks[0].pk, streaks[1].pk)
        self.assertEqual(
            MemberActivityDay.objects.filter(membership=self.member).count(), 1
        )
        streak = MemberStreak.objects.get(membership=self.member)
        self.assertEqual((streak.current_streak, streak.best_streak), (1, 1))


class PointsLedgerTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.household = Household.objects.create(name="Points household")
        self.member = Membership.objects.create(
            household=self.household,
            user=self.user_model.objects.create_user(username="scorer"),
            role=Membership.Role.MEMBER,
        )
        self.chore = Chore.objects.create(
            household=self.household,
            name="Vacuum",
            difficulty=Chore.Difficulty.EASY,
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        self.assignment = ChoreAssignment.create_manual(self.chore, self.member, occurrence=uuid.uuid4())
        self.completion = Completion.objects.create(
            household=self.household,
            chore=self.chore,
            assignment=self.assignment,
            submitted_by=self.member,
            occurrence=self.assignment.occurrence,
            status=Completion.Status.APPROVED,
            reviewer=self.member,
            reviewed_at=timezone.now(),
        )

    def test_approved_completion_creates_single_snapshot_and_totals(self):
        entry = PointsLedger.award_for_completion(self.completion)

        self.assertEqual(entry.points, 1)
        self.assertEqual(entry.member_id, self.member.id)
        self.assertEqual(entry.completion_id, self.completion.id)
        self.assertTrue(entry.awarded_at.tzinfo is not None)
        self.assertEqual(PointsLedger.total_for_member(self.member), 1)
        self.assertEqual(self.member.total_points, 1)

        self.chore.difficulty = Chore.Difficulty.HARD
        self.chore.save()
        self.assertEqual(entry.points, 1)
        self.assertEqual(PointsLedger.objects.get(pk=entry.pk).points, 1)

    def test_pending_rejected_missing_and_cross_household_are_refused(self):
        pending = Completion.objects.create(
            household=self.household,
            chore=self.chore,
            assignment=self.assignment,
            submitted_by=self.member,
            occurrence=uuid.uuid4(),
            status=Completion.Status.PENDING,
        )
        with self.assertRaises(ValidationError):
            PointsLedger.award_for_completion(pending)

        rejected = Completion.objects.create(
            household=self.household,
            chore=self.chore,
            assignment=self.assignment,
            submitted_by=self.member,
            occurrence=uuid.uuid4(),
            status=Completion.Status.REJECTED,
            reviewer=self.member,
            reviewed_at=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            PointsLedger.award_for_completion(rejected)

        with self.assertRaises(Completion.DoesNotExist):
            PointsLedger.award_for_completion(999999)

    def test_true_cross_household_invalid_completion_has_no_side_effect(self):
        other_household = Household.objects.create(name="Other points household")
        other_member = Membership.objects.create(
            household=other_household,
            user=self.user_model.objects.create_user(username="other-scorer"),
            role=Membership.Role.MEMBER,
        )
        other_chore = Chore.objects.create(
            household=other_household,
            name="Other vacuum",
            difficulty=Chore.Difficulty.EASY,
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        other_assignment = ChoreAssignment.create_manual(
            other_chore, other_member, occurrence=uuid.uuid4()
        )
        invalid = Completion.objects.create(
            household=self.household,
            chore=other_chore,
            assignment=other_assignment,
            submitted_by=other_member,
            occurrence=other_assignment.occurrence,
            status=Completion.Status.APPROVED,
            reviewer=self.member,
            reviewed_at=timezone.now(),
        )

        before = PointsLedger.objects.count()
        with self.assertRaises(ValidationError):
            PointsLedger.award_for_completion(invalid)

        self.assertEqual(PointsLedger.objects.count(), before)

    def test_duplicate_retries_are_idempotent(self):
        first = PointsLedger.award_for_completion(self.completion)
        second = PointsLedger.award_for_completion(self.completion)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(PointsLedger.objects.filter(completion=self.completion).count(), 1)

    def test_append_only_and_zero_totals_are_preserved(self):
        entry = PointsLedger.award_for_completion(self.completion)

        with self.assertRaises(ValidationError):
            entry.points = 99
            entry.save()
        with self.assertRaises(ValidationError):
            entry.delete()

        other_member = Membership.objects.create(
            household=self.household,
            user=self.user_model.objects.create_user(username="no-points"),
            role=Membership.Role.MEMBER,
        )
        self.assertEqual(PointsLedger.total_for_member(other_member), 0)
        self.assertEqual(PointsLedger.total_for_household(self.household)[self.member.id], 1)


class PointsLedgerConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        user_model = get_user_model()
        self.household = Household.objects.create(name="Concurrent points household")
        self.member = Membership.objects.create(
            household=self.household,
            user=user_model.objects.create_user(username="concurrent-scorer"),
            role=Membership.Role.MEMBER,
        )
        self.chore = Chore.objects.create(
            household=self.household,
            name="Concurrent vacuum",
            difficulty=Chore.Difficulty.EASY,
            assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        self.assignment = ChoreAssignment.create_manual(
            self.chore, self.member, occurrence=uuid.uuid4()
        )
        self.completion = Completion.objects.create(
            household=self.household,
            chore=self.chore,
            assignment=self.assignment,
            submitted_by=self.member,
            occurrence=self.assignment.occurrence,
            status=Completion.Status.APPROVED,
            reviewer=self.member,
            reviewed_at=timezone.now(),
        )

    def test_concurrent_awards_are_idempotent(self):
        barrier = threading.Barrier(2)

        def award():
            close_old_connections()
            try:
                barrier.wait()
                return PointsLedger.award_for_completion(self.completion.pk)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            awards = list(executor.map(lambda _: award(), (1, 2)))

        self.assertEqual(awards[0].pk, awards[1].pk)
        self.assertEqual(
            PointsLedger.objects.filter(completion=self.completion).count(), 1
        )

    def test_persistence_failure_rolls_back_partial_ledger_write(self):
        original_save = PointsLedger.save

        def fail_before_persist(instance, *args, **kwargs):
            raise IntegrityError("forced persistence failure")

        PointsLedger.save = fail_before_persist
        try:
            with self.assertRaises(ValidationError):
                PointsLedger.award_for_completion(self.completion.pk)
        finally:
            PointsLedger.save = original_save

        self.assertEqual(
            PointsLedger.objects.filter(completion=self.completion).count(), 0
        )


class LeaderboardAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        user_model = get_user_model()
        self.household = Household.objects.create(name="Leaderboard household")
        self.member_user = user_model.objects.create_user(username="member")
        self.tie_user = user_model.objects.create_user(username="tie")
        self.zero_user = user_model.objects.create_user(username="zero")
        self.member = Membership.objects.create(
            household=self.household, user=self.member_user, role=Membership.Role.MEMBER
        )
        self.tie = Membership.objects.create(
            household=self.household, user=self.tie_user, role=Membership.Role.MEMBER
        )
        self.zero = Membership.objects.create(
            household=self.household, user=self.zero_user, role=Membership.Role.MEMBER
        )

    def award(self, member, awarded_at, difficulty=Chore.Difficulty.EASY):
        chore = Chore.objects.create(
            household=self.household, name=uuid.uuid4().hex,
            difficulty=difficulty, assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        assignment = ChoreAssignment.create_manual(chore, member, occurrence=uuid.uuid4())
        completion = Completion.objects.create(
            household=self.household, chore=chore, assignment=assignment,
            submitted_by=member, occurrence=assignment.occurrence,
            status=Completion.Status.APPROVED, reviewer=member, reviewed_at=awarded_at,
        )
        return PointsLedger.objects.create(
            household=self.household, member=member, chore=chore,
            completion=completion, points=chore.points, awarded_at=awarded_at,
        )

    def ledger_for_status(self, member, status, awarded_at):
        chore = Chore.objects.create(
            household=self.household, name=uuid.uuid4().hex,
            difficulty=Chore.Difficulty.HARD, assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        assignment = ChoreAssignment.create_manual(chore, member, occurrence=uuid.uuid4())
        completion = Completion.objects.create(
            household=self.household, chore=chore, assignment=assignment,
            submitted_by=member, occurrence=assignment.occurrence, status=status,
            reviewer=self.tie if status != Completion.Status.PENDING else None,
            reviewed_at=awarded_at if status != Completion.Status.PENDING else None,
        )
        return PointsLedger.objects.create(
            household=self.household, member=member, chore=chore,
            completion=completion, points=chore.points, awarded_at=awarded_at,
        )

    def test_all_time_is_scoped_ranked_and_preserves_zero_members(self):
        now = timezone.now()
        self.award(self.member, now, Chore.Difficulty.HARD)
        self.award(self.tie, now, Chore.Difficulty.HARD)
        self.client.force_authenticate(self.member_user)

        response = self.client.get(reverse("leaderboard"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["view"], "all_time")
        self.assertEqual(
            [(row["member_id"], row["total_points"], row["rank"]) for row in response.data["members"]],
            [(self.member.id, 5, 1), (self.tie.id, 5, 1), (self.zero.id, 0, 3)],
        )

    @override_settings(TIME_ZONE="America/Los_Angeles")
    def test_current_period_uses_half_open_project_timezone_boundary(self):
        reference = timezone.make_aware(datetime(2026, 3, 11, 18, 0), timezone.get_current_timezone())
        local_start = timezone.make_aware(datetime(2026, 3, 9, 0, 0), timezone.get_current_timezone())
        self.award(self.member, local_start)
        self.award(self.member, local_start + timedelta(days=7))
        self.client.force_authenticate(self.member_user)

        with patch("chores.views.timezone.now", return_value=reference):
            response = self.client.get(reverse("leaderboard-current-period"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["period_type"], "calendar_week")
        self.assertEqual(response.data["members"][0]["total_points"], 1)
        self.assertEqual(response.data["period_start"], "2026-03-09T00:00:00-07:00")
        self.assertEqual(response.data["period_end"], "2026-03-16T00:00:00-07:00")

    @override_settings(TIME_ZONE="America/Los_Angeles")
    def test_leaderboards_exclude_pending_and_rejected_completions(self):
        awarded_at = timezone.make_aware(datetime(2026, 3, 11, 12, 0), timezone.get_current_timezone())
        self.ledger_for_status(self.member, Completion.Status.PENDING, awarded_at)
        self.ledger_for_status(self.member, Completion.Status.REJECTED, awarded_at)
        self.client.force_authenticate(self.member_user)

        with patch("chores.views.timezone.now", return_value=awarded_at):
            all_time = self.client.get(reverse("leaderboard"))
            current_period = self.client.get(reverse("leaderboard-current-period"))

        self.assertEqual(all_time.data["members"][0]["total_points"], 0)
        self.assertEqual(current_period.data["members"][0]["total_points"], 0)

    @override_settings(TIME_ZONE="America/Los_Angeles")
    def test_current_period_handles_fall_back_dst_transition(self):
        reference = timezone.make_aware(datetime(2026, 11, 4, 12, 0), timezone.get_current_timezone())
        before_fallback = datetime.fromisoformat("2026-11-08T08:30:00+00:00")
        after_fallback = datetime.fromisoformat("2026-11-08T09:30:00+00:00")
        self.award(self.member, before_fallback)
        self.award(self.member, after_fallback)
        self.client.force_authenticate(self.member_user)

        with patch("chores.views.timezone.now", return_value=reference):
            response = self.client.get(reverse("leaderboard-current-period"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["members"][0]["total_points"], 2)
        self.assertEqual(response.data["period_start"], "2026-11-02T00:00:00-08:00")
        self.assertEqual(response.data["period_end"], "2026-11-09T00:00:00-08:00")

    @override_settings(TIME_ZONE="America/Los_Angeles")
    def test_period_rollover_preserves_all_time_history_and_ledger(self):
        old_award = timezone.make_aware(datetime(2026, 3, 8, 23, 0), timezone.get_current_timezone())
        ledger = self.award(self.member, old_award)
        original_awarded_at = ledger.awarded_at
        self.client.force_authenticate(self.member_user)

        with patch(
            "chores.views.timezone.now",
            return_value=timezone.make_aware(datetime(2026, 3, 16, 12, 0), timezone.get_current_timezone()),
        ):
            current_period = self.client.get(reverse("leaderboard-current-period"))
            all_time = self.client.get(reverse("leaderboard"))

        self.assertEqual(current_period.data["members"][0]["total_points"], 0)
        self.assertEqual(all_time.data["members"][0]["total_points"], 1)
        ledger.refresh_from_db()
        self.assertEqual(ledger.awarded_at, original_awarded_at)

    def test_leaderboard_explicitly_isolates_other_households(self):
        other_household = Household.objects.create(name="Other leaderboard household")
        other_user = get_user_model().objects.create_user(username="other-household-member")
        other_member = Membership.objects.create(
            household=other_household, user=other_user, role=Membership.Role.MEMBER
        )
        other_chore = Chore.objects.create(
            household=other_household, name="Other chore",
            difficulty=Chore.Difficulty.HARD, assignment_mode=Chore.AssignmentMode.MANUAL,
        )
        other_assignment = ChoreAssignment.create_manual(
            other_chore, other_member, occurrence=uuid.uuid4()
        )
        other_completion = Completion.objects.create(
            household=other_household, chore=other_chore, assignment=other_assignment,
            submitted_by=other_member, occurrence=other_assignment.occurrence,
            status=Completion.Status.APPROVED, reviewer=other_member, reviewed_at=timezone.now(),
        )
        PointsLedger.objects.create(
            household=other_household, member=other_member, chore=other_chore,
            completion=other_completion, points=other_chore.points, awarded_at=timezone.now(),
        )
        self.client.force_authenticate(self.member_user)

        response = self.client.get(reverse("leaderboard"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn(other_member.id, [row["member_id"] for row in response.data["members"]])
        self.assertEqual(sum(row["total_points"] for row in response.data["members"]), 0)

    def test_inactive_and_unauthenticated_members_cannot_read(self):
        self.member.is_active = False
        self.member.save(update_fields=["is_active"])
        self.client.force_authenticate(self.member_user)
        self.assertEqual(
            self.client.get(reverse("leaderboard")).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.get(reverse("leaderboard-current-period")).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
