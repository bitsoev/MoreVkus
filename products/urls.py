from rest_framework.routers import DefaultRouter
from django.urls import path

from .views import (
    ProductViewSet, CategoryViewSet, ProductImportView,
    ProductImageViewSet, ProductImagesByProductView
)

router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'product-images', ProductImageViewSet, basename='productimage')

urlpatterns = [
    # Альтернативный способ получить изображения по товару
    path('images/<int:product_id>/', ProductImagesByProductView.as_view(), name='product-images-list'),

    # Вызов action'а viewset'а (как в твоём предыдущем варианте)
    path('product-images/by_product/<int:product_id>/',
         ProductImageViewSet.as_view({'get': 'by_product'}),
         name='product-images-by-product'),

    # Импорт товаров (Excel/CSV)
    path('product-import/', ProductImportView.as_view(), name='product-import'),

    # Роутер
    *router.urls,
]
