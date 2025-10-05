from django.utils.text import slugify
from django.db import transaction
from django.db.models import Sum
import pandas as pd

from rest_framework import viewsets, generics, status
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from rest_framework.decorators import action

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters

from .models import (
    Product, ProductImage, Category, Tag, Unit,
    Warehouse, Stock
)
from .serializers import ProductSerializer, CategorySerializer, ProductImageSerializer


class ProductImportView(APIView):
    """
    Импорт Excel (или CSV, если переименовать/подготовить).
    Ожидаемые колонки (пример):
      - SKU
      - Название
      - Описание
      - Категория
      - Теги (через запятую)
      - Цена
      - Скидочная цена
      - Вес
      - Единица (код: g, kg, pcs и т.д.)
      - Остаток
      - Склад (если есть — создаст/обновит Stock для указанного склада)
      - Активен (True/False)
      - Происхождение
      - Срок годности (Excel date)
      - MS UUID (если есть)
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAdminUser]

    def post(self, request, *args, **kwargs):
        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'Файл не передан'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            df = pd.read_excel(file)
        except Exception:
            # пытаемся прочитать как csv
            try:
                df = pd.read_csv(file)
            except Exception as e:
                return Response({'detail': f'Не удалось прочитать файл: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        created = 0
        updated = 0
        errors = []

        for idx, row in df.iterrows():
            try:
                with transaction.atomic():
                    # Категория
                    cat_name = row.get('Категория') or row.get('category') or ''
                    category = None
                    if cat_name and not pd.isna(cat_name):
                        category, _ = Category.objects.get_or_create(
                            name=str(cat_name).strip(),
                            defaults={'slug': slugify(str(cat_name))}
                        )

                    # Теги
                    tags_list = []
                    raw_tags = row.get('Теги') or row.get('tags') or ''
                    if raw_tags and not pd.isna(raw_tags):
                        tag_names = [t.strip() for t in str(raw_tags).split(',') if t.strip()]
                        for tname in tag_names:
                            tag, _ = Tag.objects.get_or_create(name=tname, defaults={'slug': slugify(tname)})
                            tags_list.append(tag)

                    # Unit
                    unit_code = row.get('Единица') or row.get('unit') or 'g'
                    unit_obj, _ = Unit.objects.get_or_create(code=str(unit_code).strip(), defaults={'name': str(unit_code)})

                    # SKU (ключ для апдейта/создания)
                    sku = row.get('SKU') or row.get('sku')
                    sku = None if (pd.isna(sku) or sku is None) else str(sku).strip()

                    # поля продукта
                    name = row.get('Название') or row.get('name') or 'Без названия'
                    description = row.get('Описание') or row.get('description') or ''
                    price = row.get('Цена') or 0
                    discount_price = row.get('Скидочная цена') if 'Скидочная цена' in row or 'discount_price' in row else None
                    weight = int(row.get('Вес') or 0)
                    stock_val = int(row.get('Остаток') or 0)
                    is_active = bool(row.get('Активен')) if 'Активен' in row else True
                    origin = row.get('Происхождение') or ''
                    ms_uuid = row.get('MS UUID') or None

                    # expiration_date может быть pd.Timestamp или строкой
                    exp_raw = row.get('Срок годности') or row.get('expiration_date')
                    expiration_date = None
                    if exp_raw and not pd.isna(exp_raw):
                        if hasattr(exp_raw, 'date'):
                            expiration_date = exp_raw.date()
                        else:
                            try:
                                expiration_date = pd.to_datetime(exp_raw).date()
                            except Exception:
                                expiration_date = None

                    defaults = {
                        'name': str(name).strip(),
                        'description': str(description),
                        'category': category,
                        'price': price,
                        'discount_price': None if (discount_price is None or (hasattr(discount_price, 'strip') and str(discount_price).strip() == '')) else discount_price,
                        'weight': weight,
                        'unit': unit_obj,
                        'stock_cache': stock_val,
                        'is_active': is_active,
                        'origin': origin,
                        'expiration_date': expiration_date,
                        'ms_uuid': None if (ms_uuid is None or pd.isna(ms_uuid)) else str(ms_uuid)
                    }

                    if sku:
                        obj, created_flag = Product.objects.update_or_create(sku=sku, defaults=defaults)
                    else:
                        # если SKU нет — создаём новый товар (но лучше иметь SKU)
                        obj = Product.objects.create(**defaults, sku=None)
                        created_flag = True

                    # Теги
                    if tags_list:
                        obj.tags.set(tags_list)

                    # Если в таблице указан Склад — обновим/создадим Stock
                    warehouse_name = row.get('Склад') or row.get('Warehouse') or None
                    if warehouse_name and not pd.isna(warehouse_name):
                        wh, _ = Warehouse.objects.get_or_create(name=str(warehouse_name).strip())
                        Stock.objects.update_or_create(product=obj, warehouse=wh, defaults={'quantity': stock_val})

                        # обновим кеш остатков
                        total = obj.stocks.aggregate(total=Sum('quantity'))['total'] or 0
                        obj.stock_cache = total
                        obj.save(update_fields=['stock_cache'])

                    # Считаем статистику
                    if created_flag:
                        created += 1
                    else:
                        updated += 1

            except Exception as e:
                errors.append({'row': int(idx), 'error': str(e)})

        return Response({'created': created, 'updated': updated, 'errors': errors})


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.filter(is_active=True).select_related('category', 'unit').prefetch_related('images', 'tags')
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = {
        'category__slug': ['exact'],
        'tags__slug': ['exact'],
        'price': ['gte', 'lte'],
        'unit__code': ['exact']
    }
    ordering_fields = ['price', 'weight', 'stock_cache']
    search_fields = ['name', 'description', 'sku']


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer


class ProductImageViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Просмотр всех изображений товаров.
    Также есть action by_product для получения изображений конкретного товара.
    """
    queryset = ProductImage.objects.all().select_related('product')
    serializer_class = ProductImageSerializer

    @action(detail=False, methods=['get'], url_path='by_product/(?P<product_id>[^/.]+)')
    def by_product(self, request, product_id=None):
        """
        Пример: /api/product-images/by_product/1/
        """
        images = ProductImage.objects.filter(product_id=product_id).order_by('-is_main', 'id')
        serializer = self.get_serializer(images, many=True, context={'request': request})
        return Response(serializer.data)


class ProductImagesByProductView(generics.ListAPIView):
    """
    Альтернативный вариант: изображения конкретного товара
    /api/images/<product_id>/
    """
    serializer_class = ProductImageSerializer

    def get_queryset(self):
        product_id = self.kwargs['product_id']
        return ProductImage.objects.filter(product_id=product_id).order_by('-is_main', 'id')
