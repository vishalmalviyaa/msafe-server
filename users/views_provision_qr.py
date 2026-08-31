import json
import qrcode
from io import BytesIO

from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from .models import EnrollmentToken, Customer
from .provisioning import build_provisioning_payload


class GenerateProvisioningQR(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, customer_id):

        customer = Customer.objects.filter(id=customer_id).first()

        if not customer:
            return HttpResponse("Customer not found", status=404)

        manager_profile = getattr(request.user, "manager_profile", None)

        if manager_profile is None:
            return HttpResponse("Only managers can generate provisioning QR codes.", status=403)

        token = EnrollmentToken.objects.create(
            token=EnrollmentToken.generate_token(),
            manager=manager_profile,
            customer=customer,
        )

        device = getattr(customer, "device", None)

        payload = build_provisioning_payload(
            token=token.token,
            manager_id=manager_profile.id,
            imei1=device.imei1 if device else None,
        )

        qr = qrcode.make(json.dumps(payload))

        buffer = BytesIO()
        qr.save(buffer)

        response = HttpResponse(buffer.getvalue(), content_type="image/png")
        response["Cache-Control"] = "no-store"
        return response
