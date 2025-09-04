from rest_framework import viewsets
from .models import Product, Category
from .serializers import ProductSerializer, CategorySerializer
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
import pandas as pd
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser

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

