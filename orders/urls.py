from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CreateOrderView, OrderRepeatView, OrderViewSet, OrderListView, OrderDetailView, cancel_order

router = DefaultRouter()
router.register(r'orders', OrderViewSet, basename='order')

urlpatterns = [
    path('create/', CreateOrderView.as_view(), name='create-order'),
    path('<int:pk>/cancel/', cancel_order, name='cancel-order'),
    path('<int:pk>/repeat/', OrderRepeatView.as_view(), name='order-repeat'),
    path('orders/', OrderListView.as_view(), name='order-list'),
    path('orders/<int:pk>/', OrderDetailView.as_view(), name='order-detail'),
    path('api/', include(router.urls)),
]
