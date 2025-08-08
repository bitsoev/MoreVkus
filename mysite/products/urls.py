from rest_framework.routers import DefaultRouter
from .views import ProductViewSet, CategoryViewSet, ProductImportView
from django.urls import path

router = DefaultRouter()
router.register(r'products', ProductViewSet)
router.register(r'categories', CategoryViewSet)

urlpatterns = [
    path('product-import/', ProductImportView.as_view(), name='product-import'),
    *router.urls,
]