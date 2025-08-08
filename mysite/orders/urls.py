from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import CreateOrderView, RettUser, UpdateOrdersView, OrderViewSet, OrderRepeatView

router = DefaultRouter()
router.register(r'orders', OrderViewSet, basename='order')

urlpatterns = [
    path('<int:pk>/repeat/', OrderRepeatView.as_view(), name='order-repeat'),
    path('api/createorder/', CreateOrderView.as_view(), name='api_create_order'),
    path('api/updateorder/', UpdateOrdersView.as_view(), name='api_update_order'),
    path('api/rettuser/', RettUser, name='Rett_User'),
    path('api/', include(router.urls)),
]