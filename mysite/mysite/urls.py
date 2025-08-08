from django.contrib import admin
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter
from django.urls import include, path



urlpatterns = [
    path('api-token-auth/', obtain_auth_token, name='api_token_auth'),
    path("orders/", include("orders.urls")),
    path("admin/", admin.site.urls),
    path("catalog/", include("catalog.urls")),
    path('accounts/', include("django.contrib.auth.urls")),
    #path('users/', include("users.urls", namespace='users')),
    path('users/', include('users.urls')),
    path('products/', include('products.urls')),
]
