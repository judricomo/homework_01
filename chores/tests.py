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

from .models import Household, Membership


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
