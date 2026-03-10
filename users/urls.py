from django.urls import path
from .views import (
    DeviceHeartbeatView,
    DPCUnenrollAckView,
    DPCEnrollView,
    S3UploadUrlView,
    DPCLockStatusAckView,
)

urlpatterns = [
    path("dpc/heartbeat/", DeviceHeartbeatView.as_view(), name="dpc-heartbeat"),
    path("dpc/unenroll_ack/", DPCUnenrollAckView.as_view(), name="dpc-unenroll-ack"),
    path("dpc/enroll/", DPCEnrollView.as_view(), name="dpc-enroll"),
    path("dpc/lock_status_ack/", DPCLockStatusAckView.as_view(), name="dpc-lock-status-ack"),
    path("uploads/url/", S3UploadUrlView.as_view(), name="s3-upload-url"),
]
