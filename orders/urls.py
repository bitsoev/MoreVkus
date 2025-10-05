from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CreateOrderView, OrderRepeatView, OrderViewSet, OrderListView, OrderDetailView

router = DefaultRouter()
router.register(r'orders', OrderViewSet, basename='order')

urlpatterns = [
    path('api/createorder/', CreateOrderView.as_view(), name='api_create_order'),
    path('api/orders/<int:pk>/repeat/', OrderRepeatView.as_view(), name='order-repeat'),
    path('api/orders/', OrderListView.as_view(), name='order-list'),
    path('api/orders/<int:pk>/', OrderDetailView.as_view(), name='order-detail'),
    path('api/', include(router.urls)),
]
