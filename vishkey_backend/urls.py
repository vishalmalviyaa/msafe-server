from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [

    path('', lambda request: HttpResponse("✅ VishKey Backend Running")),

    path('admin/', admin.site.urls),

    # JWT auth
    path('api/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Apps
    path('api/owner/', include('owner.urls')),
    path('api/manager/', include('manager.urls')),
    path('api/', include('users.urls')),

    path('api/system/', include('scalability_core.urls')),
]