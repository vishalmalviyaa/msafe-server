import json
import hashlib
import requests
import qrcode
from io import BytesIO

from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from .models import EnrollmentToken, Customer


APK_URL = "https://yourdomain.com/msafe.apk"


def get_apk_checksum():
    r = requests.get(APK_URL)
    sha256 = hashlib.sha256(r.content).hexdigest()
    return sha256


class GenerateProvisioningQR(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, customer_id):

        customer = Customer.objects.get(id=customer_id)

        token = EnrollmentToken.objects.create(
            token=EnrollmentToken.generate_token(),
            manager=request.user.manager_profile,
            customer=customer
        )

        payload = {
            "android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME":
            "com.vashu.msafe.agent/.receiver.DeviceAdminReceiver",

            "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION":
            APK_URL,

            "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_CHECKSUM":
            get_apk_checksum(),

            "android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE": {
                "token": token.token,
                "manager_id": request.user.manager_profile.id,
                "server": "https://api.msafe.in"
            }
        }

        qr = qrcode.make(json.dumps(payload))

        buffer = BytesIO()
        qr.save(buffer)

        return HttpResponse(buffer.getvalue(), content_type="image/png")