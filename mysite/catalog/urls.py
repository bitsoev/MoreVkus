from . import views
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProductViewSet,InStockViewSet

router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')
router.register(r'productsinstock',InStockViewSet,basename='instock')


urlpatterns = [
    path('chek_stock/<int:product_id>/', views.chek_product_stock),
    path('add_to_cart/<int:product_id>/', views.add_to_cart),
    path('testing/<int:pk>/', views.testing),
    path('testing_2/',views.testing_2),
    path('testing_3/',views.testing_3),
    path('api/', include(router.urls)),
]