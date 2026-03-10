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

    path("health/", health),

    path("devices/register/", DeviceRegisterView.as_view()),

    path("devices/heartbeat/", DeviceHeartbeatView.as_view()),

    path("devices/location/", DeviceLocationPingView.as_view()),

    path("devices/ack/", DeviceAckView.as_view()),

    path("uploads/presign/", PresignUploadView.as_view()),

]