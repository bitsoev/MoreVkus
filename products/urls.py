from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import ProductViewSet, CategoryViewSet, ProductImportView, ProductImageViewSet, PriceTypeViewSet

router = DefaultRouter()
router.register(r'products', ProductViewSet)
router.register(r'categories', CategoryViewSet)
router.register(r'price-types', PriceTypeViewSet, basename='pricetype')
router.register(r'product-images', ProductImageViewSet, basename='productimage')

urlpatterns = [
    path('product-import/', ProductImportView.as_view(), name='product-import'),
    *router.urls,
]
