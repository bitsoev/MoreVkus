from django.conf.urls.static import static
from django.contrib import admin
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter
from django.urls import include, path

from mysite import settings
from mysite.settings import DEBUG, MEDIA_URL

urlpatterns = [
    path('api-token-auth/', obtain_auth_token, name='api_token_auth'),
    path("orders/", include("orders.urls")),
    path("admin/", admin.site.urls),
    path('accounts/', include("django.contrib.auth.urls")),
    #path('users/', include("users.urls", namespace='users')),
    path('users/', include('users.urls')),
    path('products/', include('products.urls')),
]

if DEBUG:
    urlpatterns += static(MEDIA_URL, document_root=settings.MEDIA_ROOT)