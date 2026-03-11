from rest_framework import serializers

from manager.models import ManagerProfile
from manager.serializers import ManagerProfileSerializer
from users.serializers import CustomerSerializer

from .models import OwnerProfile


class OwnerManagerSerializer(ManagerProfileSerializer):

    class Meta(ManagerProfileSerializer.Meta):
        fields = ManagerProfileSerializer.Meta.fields + ["id"]


class OwnerProfileSerializer(serializers.ModelSerializer):

    username = serializers.CharField(source="user.username")

    class Meta:
        model = OwnerProfile
        fields = [
            "id",
            "username",
            "phone",
            "photo",
        ]