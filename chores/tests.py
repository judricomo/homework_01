from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import SimpleTestCase
from django.test import TestCase
from django.urls import reverse

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
