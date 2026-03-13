from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ManagerCustomerViewSet, ManagerProfileViewSet
from .views import ManagerDashboardView
from .views import ManagerDeviceMapView
from .views import download_agent
router = DefaultRouter()
router.register(r"users", ManagerCustomerViewSet, basename="manager-users")
router.register(r"profile", ManagerProfileViewSet, basename="manager-profile")

urlpatterns = [
    path("", include(router.urls)),
    path("dashboard/", ManagerDashboardView.as_view()),
    path("devices/map/", ManagerDeviceMapView.as_view()),
    path("download/msafe-agent.apk", download_agent),
]
