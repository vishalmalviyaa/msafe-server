import json
import qrcode
from io import BytesIO

from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from .models import EnrollmentToken, Customer


APK_URL = "https://api.msafe.shop/download/msafe-agent.apk"

APK_CHECKSUM = "baab5d65de30674600ccfb2d28d2526c8b459885c76042d4857cd621602b7afe"


class GenerateProvisioningQR(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, customer_id):

        customer = Customer.objects.filter(id=customer_id).first()

        if not customer:
            return HttpResponse("Customer not found", status=404)

        token = EnrollmentToken.objects.create(
            token=EnrollmentToken.generate_token(),
            manager=request.user.manager_profile,
            customer=customer
        )

        payload = {

            "android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME":
            "com.vashu.msafe.agent/.receiver.DeviceAdminReceiver",

            "android.app.extra.PROVISIONING_SKIP_ENCRYPTION": True,

            "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION":
            APK_URL,

            "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_CHECKSUM":
            APK_CHECKSUM,

            "android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE": {
                "token": token.token,
                "manager_id": request.user.manager_profile.id,
                "server": "https://api.msafe.shop"
            }
        }

        qr = qrcode.make(json.dumps(payload))

        buffer = BytesIO()
        qr.save(buffer)

        return HttpResponse(buffer.getvalue(), content_type="image/png")