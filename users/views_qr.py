import secrets
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import EnrollmentToken, Customer


class GenerateEnrollmentTokenView(APIView):
    """
    POST /api/enroll/token/

    BODY:
    {
        "customer_id": 10
    }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):

        customer_id = request.data.get("customer_id")

        if not customer_id:
            return Response(
                {"detail": "customer_id required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        customer = Customer.objects.filter(id=customer_id).first()

        if not customer:
            return Response(
                {"detail": "Customer not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        manager_profile = request.user.manager_profile

        if customer.manager != manager_profile:
            return Response(
                {"detail": "Forbidden"},
                status=status.HTTP_403_FORBIDDEN,
            )

        token = secrets.token_urlsafe(32)

        et = EnrollmentToken.objects.create(
            token=token,
            manager=manager_profile,
            customer=customer,
            expires_at=timezone.now() + timezone.timedelta(minutes=10)
        )

        return Response({
            "token": et.token,
            "manager_id": manager_profile.id,
            "expires_at": et.expires_at
        })