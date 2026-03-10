from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ManagerCustomerViewSet, ManagerProfileViewSet

router = DefaultRouter()
router.register(r"users", ManagerCustomerViewSet, basename="manager-users")
router.register(r"profile", ManagerProfileViewSet, basename="manager-profile")

urlpatterns = [
    path("", include(router.urls)),
]
