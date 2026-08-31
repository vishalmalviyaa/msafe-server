"""
Single source of truth for Android Enterprise "Device Owner" provisioning
QR payloads.

There used to be two independent copies of this payload (one in
users/views_provision_qr.py, one in manager/views.py's qr_png action) with
DIFFERENT component names, checksums, and APK download URLs. At most one of
those could have ever actually worked - Android's provisioning flow fails
outright on a checksum/component mismatch. Both views now import from here
instead.

IMPORTANT: APK_CHECKSUM below is a placeholder. Replace it with the real
SHA-256 checksum of your signed msafe-agent.apk before relying on QR
provisioning, e.g.:

    shasum -a 256 msafe-agent.apk | cut -d' ' -f1 | xxd -r -p | base64

(Android Enterprise expects the checksum in a specific base64/hex form
depending on Android version - see Android's "Provision a device with
DPC identifier" docs for the exact encoding your target OS versions need.)
"""

# Must exactly match the DeviceAdminReceiver declared in the agent APK's
# AndroidManifest.xml.
DEVICE_ADMIN_COMPONENT_NAME = "com.vashu.msafe.agent/.receiver.DeviceAdminReceiver"

APK_DOWNLOAD_URL = "https://api.msafe.shop/api/manager/download/msafe-agent.apk"

# PLACEHOLDER - replace with the real signed APK's checksum.
APK_CHECKSUM = "e2ce4a93bf38bc210a30266a10673e4b6eafe3c3554945e78c13fa0d0a277c6f"


def build_provisioning_payload(token: str, manager_id: int, imei1: str | None = None) -> dict:
    extras = {
        "token": token,
        "manager_id": manager_id,
        "server": "https://api.msafe.shop",
    }
    if imei1:
        extras["imei1"] = imei1

    return {
        "android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME": DEVICE_ADMIN_COMPONENT_NAME,
        "android.app.extra.PROVISIONING_SKIP_ENCRYPTION": True,
        "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION": APK_DOWNLOAD_URL,
        "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_CHECKSUM": APK_CHECKSUM,
        "android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE": extras,
    }
