from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import ManagerProfile

User = get_user_model()


class ManagerProfileSerializer(serializers.ModelSerializer):

    username = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True)
    email = serializers.EmailField(required=False, allow_blank=True)

    keys_remaining = serializers.SerializerMethodField()

    class Meta:
        model = ManagerProfile
        fields = [
            "id",
            "username",
            "password",
            "email",
            "phone",
            "photo",
            "default_lock_message",
            "default_lock_logo",
            "total_keys",
            "used_keys",
            "keys_remaining",
        ]

        read_only_fields = [
            "total_keys",
            "used_keys",
            "keys_remaining",
        ]

    def get_keys_remaining(self, obj):
        return obj.keys_remaining()

    def create(self, validated_data):

        username = validated_data.pop("username")
        password = validated_data.pop("password")
        email = validated_data.pop("email", "")

        user = User.objects.create_user(
            username=username,
            password=password,
            email=email,
        )

        manager = ManagerProfile.objects.create(
            user=user,
            **validated_data
        )

        return manager