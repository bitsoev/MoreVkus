from .models import Product, ProductImage, Category
from .serializers import ProductSerializer, CategorySerializer
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
import pandas as pd
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from rest_framework import viewsets, generics
from rest_framework.decorators import action
from .serializers import ProductImageSerializer


class ProductImportView(APIView):
    parser_classes = [MultiPartParser]
    permission_classes = [IsAdminUser]

    def post(self, request, *args, **kwargs):
        file = request.FILES['file']
        df = pd.read_excel(file)

        for _, row in df.iterrows():
            category, _ = Category.objects.get_or_create(name=row['Категория'], slug=row['Категория'].lower().replace(" ", "-"))
            Product.objects.create(
                name=row['Название'],
                description=row.get('Описание', ''),
                category=category,
                price=row['Цена'],
                weight=row['Вес'],
                stock=row.get('Остаток', 0),
                is_active=row.get('Активен', True)
            )

        return Response({"status": "Импорт завершен"})


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.filter(is_active=True).prefetch_related('images', 'tags', 'category')
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = {
        'category__slug': ['exact'],
        'tags__slug': ['exact'],
        'price': ['gte', 'lte']
    }
    ordering_fields = ['price', 'weight']


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer


class ProductImageViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Просмотр всех изображений товаров
    """
    queryset = ProductImage.objects.all()
    serializer_class = ProductImageSerializer

    @action(detail=False, methods=['get'])
    def by_product(self, request, product_id=None):
        """
        Получить все изображения для конкретного товара
        Пример: /api/product-images/by_product/1/
        """
        images = ProductImage.objects.filter(product_id=product_id)
        serializer = self.get_serializer(images, many=True)
        return Response(serializer.data)


class ProductImagesByProductView(generics.ListAPIView):
    """
    Альтернативный вариант: изображения конкретного товара
    """
    serializer_class = ProductImageSerializer

    def get_queryset(self):
        product_id = self.kwargs['product_id']
        return ProductImage.objects.filter(product_id=product_id)