from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import ManagerProfile

User = get_user_model()


class ManagerProfileSerializer(serializers.ModelSerializer):

    # Only required when *creating* a manager (a new User has to be made).
    # Optional on update, since you're not obligated to change your
    # username/password every time you edit your profile.
    username = serializers.CharField(write_only=True, required=False)
    password = serializers.CharField(write_only=True, required=False)
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

    def validate(self, attrs):
        # username/password are mandatory on create (need them to make the
        # underlying User), but optional on update.
        if self.instance is None:
            if not attrs.get("username"):
                raise serializers.ValidationError({"username": "This field is required."})
            if not attrs.get("password"):
                raise serializers.ValidationError({"password": "This field is required."})
        return attrs

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

    def update(self, instance, validated_data):
        # These three belong to the related User, not to ManagerProfile
        # itself - the base ModelSerializer.update() would otherwise try
        # (and silently fail) to set them directly on the profile instance.
        username = validated_data.pop("username", None)
        password = validated_data.pop("password", None)
        email = validated_data.pop("email", None)

        user_fields = []
        if username:
            instance.user.username = username
            user_fields.append("username")
        if email is not None:
            instance.user.email = email
            user_fields.append("email")
        if password:
            instance.user.set_password(password)
            user_fields.append("password")

        if user_fields:
            instance.user.save(update_fields=user_fields)

        return super().update(instance, validated_data)
