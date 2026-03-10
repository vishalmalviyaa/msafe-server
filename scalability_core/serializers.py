from rest_framework import serializers

from .models import DeviceRegistration, FcmCommand, CommandAck, AuditLog, LocationPing


class DeviceRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceRegistration
        fields = [
            "id",
            "user",
            "manager_id",
            "imei_1",
            "imei_2",
            "device_id",
            "fcm_token",
            "last_seen",
            "last_ip",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CommandAckSerializer(serializers.Serializer):
    action = serializers.CharField()
    command_id = serializers.IntegerField(required=False)
    fcm_message_id = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField()
    payload = serializers.JSONField(required=False)


class PresignUploadRequestSerializer(serializers.Serializer):
    filename = serializers.CharField()
    content_type = serializers.CharField()


class PresignUploadResponseSerializer(serializers.Serializer):
    url = serializers.CharField()
    fields = serializers.JSONField()


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = "__all__"


class LocationPingSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocationPing
        fields = "__all__"
