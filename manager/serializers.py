from rest_framework import serializers
from .models import ManagerProfile


class ManagerProfileSerializer(serializers.ModelSerializer):
    keys_remaining = serializers.SerializerMethodField()

    class Meta:
        model = ManagerProfile
        fields = [
            "id",
            "phone",
            "photo",
            "default_lock_message",
            "default_lock_logo",
            "total_keys",
            "used_keys",
            "keys_remaining",
        ]
        read_only_fields = ["total_keys", "used_keys", "keys_remaining"]

    def get_keys_remaining(self, obj):
        return obj.keys_remaining()
