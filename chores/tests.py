from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import SimpleTestCase
from django.test import TestCase
from django.urls import path, reverse
from django.test import override_settings
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework.views import APIView

from .models import Chore, ChoreAssignment, Household, Membership, RotationMember


class ProjectLoadsTest(SimpleTestCase):
    def test_admin_login_page_loads(self):
        response = self.client.get(reverse("admin:login"))

        self.assertEqual(response.status_code, 200)


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


class ChoreAssignmentTests(TestCase):
    def setUp(self):
        self.household = Household.objects.create(name="Assignments")
        self.user = get_user_model().objects.create_user(username="assignable")
        self.member = Membership.objects.create(
            household=self.household, user=self.user, role=Membership.Role.MEMBER
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
