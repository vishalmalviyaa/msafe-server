from django.urls import path

from .views import (
    health,
    DeviceAckView,
    PresignUploadView,
    DeviceRegisterView,
    DeviceHeartbeatView,
    DeviceLocationPingView,
)

app_name = "scalability_core"

urlpatterns = [

    path("health/", health, name="health"),

    path(
        "devices/register/",
        DeviceRegisterView.as_view(),
        name="device-register",
    ),

    path(
        "devices/heartbeat/",
        DeviceHeartbeatView.as_view(),
        name="device-heartbeat",
    ),

    path(
        "devices/location/",
        DeviceLocationPingView.as_view(),
        name="device-location",
    ),

    path(
        "devices/ack/",
        DeviceAckView.as_view(),
        name="device-ack",
    ),

    path(
        "uploads/presign/",
        PresignUploadView.as_view(),
        name="presign-upload",
    ),
]