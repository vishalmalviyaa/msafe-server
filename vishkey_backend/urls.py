from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from manager.views import download_agent
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [

    path("", lambda request: HttpResponse("✅ VishKey Backend Running")),

    path("download/msafe-agent.apk", download_agent),

    path("admin/", admin.site.urls),

    path("api/auth/token/", TokenObtainPairView.as_view()),
    path("api/auth/token/refresh/", TokenRefreshView.as_view()),

    path("api/owner/", include("owner.urls")),
    path("api/manager/", include("manager.urls")),
    path("api/", include("users.urls")),
    path("api/system/", include("scalability_core.urls")),
]