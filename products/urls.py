from rest_framework.routers import DefaultRouter
from .views import ProductViewSet, CategoryViewSet, ProductImportView, ProductImageViewSet, ProductImagesByProductView
from django.urls import path

router = DefaultRouter()
router.register(r'products', ProductViewSet)
router.register(r'categories', CategoryViewSet)
router.register(r'product-images', ProductImageViewSet, basename='productimage')


urlpatterns = [
    path('images/<int:product_id>/',
         ProductImagesByProductView.as_view(),
         name='product-images-list'),
    path('product-images/by_product/<int:product_id>/',
         ProductImageViewSet.as_view({'get': 'by_product'}),
         name='product-images-by-product'),
    path('product-import/', ProductImportView.as_view(), name='product-import'),
    *router.urls,
]