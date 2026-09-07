from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Membership


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
