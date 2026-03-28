from rest_framework import serializers
from .models import Customer, Device, EnrollmentToken, AuditLog
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from manager.models import ManagerProfile


class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = [
            "id",
            "imei1",
            "imei2",
            "mobile_name",
            "mobile_number",
            "sim1_number",
            "sim2_number",
            "last_location_lat",
            "last_location_lng",
            "last_location_time",
            "lock_status",
            "dpc_status",
            "last_seen_at",
        ]
        read_only_fields = [
            "last_location_lat",
            "last_location_lng",
            "last_location_time",
            "last_seen_at",
            "lock_status",
            "dpc_status",
        ]


class CustomerSerializer(serializers.ModelSerializer):
    device = DeviceSerializer(read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "phone",
            "address",
            "loan_amount",
            "emi_amount",
            "emi_start_date",
            "emi_end_date",
            "photo",
            "signature",
            "is_active",
            "device",
        ]


class CustomerCreateUpdateSerializer(serializers.ModelSerializer):
    """
    For Manager: create / update customer and attach device.
    IMEI fields are write-only and immutable after creation.
    """
    imei1 = serializers.CharField(write_only=True)
    imei2 = serializers.CharField(write_only=True, required=False, allow_blank=True)
    mobile_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    mobile_number = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "phone",
            "address",
            "loan_amount",
            "emi_amount",
            "emi_start_date",
            "emi_end_date",
            "photo",
            "signature",
            "imei1",
            "imei2",
            "mobile_name",
            "mobile_number",
        ]

    def create(self, validated_data):
        request = self.context["request"]
        manager_profile = request.user.manager_profile

        imei1 = validated_data.pop("imei1")
        imei2 = validated_data.pop("imei2", "")
        mobile_name = validated_data.pop("mobile_name", "")
        mobile_number = validated_data.pop("mobile_number", "")

        customer = Customer.objects.create(manager=manager_profile, **validated_data)
        Device.objects.create(
            customer=customer,
            imei1=imei1,
            imei2=imei2 or None,
            mobile_name=mobile_name,
            mobile_number=mobile_number,
        )
        return customer

    def update(self, instance, validated_data):
        # IMEI + mobile fields not editable here
        validated_data.pop("imei1", None)
        validated_data.pop("imei2", None)
        validated_data.pop("mobile_name", None)
        validated_data.pop("mobile_number", None)
        return super().update(instance, validated_data)


class DeviceHeartbeatSerializer(serializers.Serializer):
    imei1 = serializers.CharField()
    imei2 = serializers.CharField(required=False, allow_blank=True)
    sim1_number = serializers.CharField(required=False, allow_blank=True)
    sim2_number = serializers.CharField(required=False, allow_blank=True)
    lat = serializers.FloatField(required=False)
    lng = serializers.FloatField(required=False)
    fcm_token = serializers.CharField(required=False, allow_blank=True)


class DPCEnrollSerializer(serializers.Serializer):
    token = serializers.CharField()
    manager_id = serializers.IntegerField()
    imei1 = serializers.CharField()
    imei2 = serializers.CharField(required=False, allow_blank=True)
    fcm_token = serializers.CharField(required=False, allow_blank=True)


class EnrollmentTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnrollmentToken
        fields = ["token", "status", "expires_at", "customer_id", "manager_id"]
        read_only_fields = ["status", "customer_id", "manager_id"]


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = "__all__"


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        manager_profile = ManagerProfile.objects.filter(user=user).first()

        token["username"] = user.username
        token["is_owner"] = user.is_superuser or user.is_staff
        token["is_manager"] = manager_profile is not None
        token["manager_id"] = manager_profile.id if manager_profile else None

        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        manager_profile = ManagerProfile.objects.filter(user=self.user).first()

        data["username"] = self.user.username
        data["is_owner"] = self.user.is_superuser or self.user.is_staff
        data["is_manager"] = manager_profile is not None
        data["manager_id"] = manager_profile.id if manager_profile else None

        return data