from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Device


class ManagerDeviceMapView(APIView):
    """
    Manager sees only their customers devices
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):

        manager = request.user.manager_profile

        devices = Device.objects.select_related("customer").filter(
            customer__manager=manager,
            customer__is_active=True
        )

        data = []

        for device in devices:

            online = cache.get(f"device_online:{device.imei1}") or False

            data.append({
                "customer_id": device.customer.id,
                "customer_name": device.customer.name,
                "imei1": device.imei1,

                "lat": device.last_location_lat,
                "lng": device.last_location_lng,

                "sim1": device.sim1_number,
                "sim2": device.sim2_number,

                "online": online,
                "last_seen": device.last_seen_at,
            })

        return Response({"devices": data})


class OwnerDeviceMapView(APIView):
    """
    Owner sees ALL devices
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):

        devices = Device.objects.select_related("customer", "customer__manager")

        data = []

        for device in devices:

            online = cache.get(f"device_online:{device.imei1}") or False

            data.append({
                "manager": device.customer.manager.user.username,
                "customer_id": device.customer.id,
                "customer_name": device.customer.name,
                "imei1": device.imei1,

                "lat": device.last_location_lat,
                "lng": device.last_location_lng,

                "online": online,
                "last_seen": device.last_seen_at,
            })

        return Response({"devices": data})