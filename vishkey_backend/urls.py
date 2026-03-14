from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from manager.views import download_agent

urlpatterns = [

    path('', lambda request: HttpResponse("✅ VishKey Backend Running")),

    # APK DOWNLOAD
    path('download/msafe-agent.apk', download_agent),

    path('admin/', admin.site.urls),

    # JWT auth
    path('api/auth/token/', TokenObtainPairView.as_view()),
    path('api/auth/token/refresh/', TokenRefreshView.as_view()),

    # Apps
    path('api/owner/', include('owner.urls')),
    path('api/manager/', include('manager.urls')),
    path('api/', include('users.urls')),
    path('api/system/', include('scalability_core.urls')),
]