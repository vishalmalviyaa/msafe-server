from django.urls import path

from .views_provision_qr import GenerateProvisioningQR
from .views_commands import PendingDeviceCommandsView
from .views import (
    DeviceHeartbeatView,
    DPCUnenrollAckView,
    DPCEnrollView,
    S3UploadUrlView,
    DPCLockStatusAckView,
)

from .views_commands import SendDeviceCommandView
from .views_qr import GenerateEnrollmentTokenView
from .views_device_map import ManagerDeviceMapView, OwnerDeviceMapView
from django.urls import path
from .views import auth_me

urlpatterns = [
    path("auth/me/", auth_me),
]

urlpatterns = [
    path("auth/me/", auth_me),

    # -------------------------
    # DPC DEVICE APIs
    # -------------------------

    path(
        "dpc/heartbeat/",
        DeviceHeartbeatView.as_view(),
        name="dpc-heartbeat"
    ),

    path(
        "dpc/enroll/",
        DPCEnrollView.as_view(),
        name="dpc-enroll"
    ),

    path(
        "dpc/unenroll_ack/",
        DPCUnenrollAckView.as_view(),
        name="dpc-unenroll-ack"
    ),

    path(
        "dpc/lock_status_ack/",
        DPCLockStatusAckView.as_view(),
        name="dpc-lock-status-ack"
    ),

    # -------------------------
    # FILE UPLOAD (S3)
    # -------------------------

    path(
        "uploads/url/",
        S3UploadUrlView.as_view(),
        name="s3-upload-url"
    ),

    # -------------------------
    # DEVICE COMMANDS
    # -------------------------

    path(
        "device/command/",
        SendDeviceCommandView.as_view(),
        name="device-command"
    ),

    # -------------------------
    # ENROLLMENT TOKEN / QR
    # -------------------------

    path(
        "enroll/token/",
        GenerateEnrollmentTokenView.as_view(),
        name="generate-enroll-token"
    ),

    path(
        "provision/qr/<int:customer_id>/",
        GenerateProvisioningQR.as_view(),
        name="provision-qr"
    ),

    # -------------------------
    # DEVICE MAPs
    # -------------------------

    path(
        "manager/device-map/",
        ManagerDeviceMapView.as_view(),
        name="manager-device-map"
    ),

    path(
        "owner/device-map/",
        OwnerDeviceMapView.as_view(),
        name="owner-device-map"
    ),
    path(
    "device/pending-commands/",
    PendingDeviceCommandsView.as_view(),
    name="pending-device-commands"
)
]