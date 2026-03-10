from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OwnerCustomerViewSet, OwnerManagerViewSet, OwnerForceDeleteUserView
from .views import OwnerProfileView
router = DefaultRouter()
router.register(r"users", OwnerCustomerViewSet, basename="owner-users")
router.register(r"managers", OwnerManagerViewSet, basename="owner-managers")

urlpatterns = [
    path("", include(router.urls)),
    path("users/<int:pk>/force_delete/", OwnerForceDeleteUserView.as_view(), name="owner-force-delete"),
     path("profile/", OwnerProfileView.as_view()),
]
