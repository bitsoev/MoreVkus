from django.utils import timezone
from django.utils.text import slugify
from django.db import transaction
from django.db.models import Sum
import pandas as pd
from django.db import models

from rest_framework import viewsets, generics, status, filters
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, AllowAny
from rest_framework.decorators import action

from django_filters.rest_framework import DjangoFilterBackend

from .models import Product, ProductImage, Category, Tag, Unit, Warehouse, Stock, PriceType, Price
from .serializers import ProductSerializer, CategorySerializer, ProductImageSerializer, PriceTypeSerializer, \
    ProductPriceSerializer


class ProductImportView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAdminUser]
    BASE_PRICE_TYPE_CODE = "base"

    def post(self, request, *args, **kwargs):
        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'Файл не передан'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            df = pd.read_excel(file)
        except Exception:
            try:
                df = pd.read_csv(file)
            except Exception as e:
                return Response({'detail': f'Не удалось прочитать файл: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        base_price_type, _ = PriceType.objects.get_or_create(code=self.BASE_PRICE_TYPE_CODE, defaults={'name': 'Базовая цена'})

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
                    unit_code = row.get('Единица') or row.get('unit') or 'pcs'
                    unit_obj, _ = Unit.objects.get_or_create(code=str(unit_code).strip(), defaults={'name': str(unit_code)})

                    # SKU
                    sku = row.get('SKU') or row.get('sku')
                    sku = None if (pd.isna(sku) or sku is None) else str(sku).strip()

                    # fields
                    name = row.get('Название') or row.get('name') or 'Без названия'
                    description = row.get('Описание') or row.get('description') or ''
                    weight = int(row.get('Вес') or 0)
                    stock_val = int(row.get('Остаток') or 0)
                    is_active = bool(row.get('Активен')) if 'Активен' in row else True
                    origin = row.get('Происхождение') or ''
                    ms_uuid = row.get('MS UUID') or None

                    exp_raw = row.get('Срок годности') or row.get('expiration_date')
                    expiration_date = None
                    if exp_raw and not pd.isna(exp_raw):
                        try:
                            expiration_date = pd.to_datetime(exp_raw).date()
                        except Exception:
                            expiration_date = None

                    defaults = {
                        'name': str(name).strip(),
                        'description': str(description),
                        'category': category,
                        'unit': unit_obj,
                        'weight': weight,
                        'stock_cache': stock_val,
                        'is_active': is_active,
                        'origin': origin,
                        'expiration_date': expiration_date,
                        'ms_uuid': None if (ms_uuid is None or pd.isna(ms_uuid)) else str(ms_uuid)
                    }

                    if sku:
                        obj, created_flag = Product.objects.update_or_create(sku=sku, defaults=defaults)
                    else:
                        obj = Product.objects.create(**defaults, sku=str(uuid.uuid4()))
                        created_flag = True

                    # tags
                    if tags_list:
                        obj.tags.set(tags_list)

                    # price
                    raw_price = row.get('Цена') or row.get('price')
                    if raw_price and not pd.isna(raw_price):
                        Price.objects.update_or_create(product=obj, price_type=base_price_type, defaults={'value': raw_price, 'start_date': timezone.now(), 'is_active': True})

                    # warehouse + stock
                    warehouse_name = row.get('Склад') or row.get('Warehouse') or None
                    if warehouse_name and not pd.isna(warehouse_name):
                        wh, _ = Warehouse.objects.get_or_create(name=str(warehouse_name).strip())
                        Stock.objects.update_or_create(product=obj, warehouse=wh, defaults={'quantity': stock_val})
                        total = obj.stocks.aggregate(total=Sum('quantity'))['total'] or 0
                        obj.stock_cache = total
                        obj.save(update_fields=['stock_cache'])

                    if created_flag:
                        created += 1
                    else:
                        updated += 1

            except Exception as e:
                errors.append({'row': int(idx), 'error': str(e)})

        return Response({'created': created, 'updated': updated, 'errors': errors})


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.filter(is_active=True).select_related(
        'category', 'unit'
    ).prefetch_related(
        'images', 'tags', 'prices__price_type'
    )
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = {
        'category__slug': ['exact'],
        'tags__slug': ['exact'],
        'unit__code': ['exact'],
        'prices__price_type__code': ['exact'],  # Фильтр по типу цены
    }
    ordering_fields = ['name', 'stock_cache', 'created_at']
    search_fields = ['name', 'description', 'sku']

    @action(detail=True, methods=['get'])
    def price_history(self, request, pk=None):
        """Получить историю цен для товара"""
        product = self.get_object()
        prices = Price.objects.filter(
            product=product
        ).select_related('price_type').order_by('-start_date')

        serializer = ProductPriceSerializer(prices, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def with_price_type(self, request):
        """Получить товары с конкретным типом цены"""
        price_type_code = request.query_params.get('price_type')
        if not price_type_code:
            return Response(
                {'error': 'price_type parameter is required'},
                status=400
            )

        try:
            price_type = PriceType.objects.get(code=price_type_code)
        except PriceType.DoesNotExist:
            return Response(
                {'error': 'Price type not found'},
                status=404
            )

        # Получаем товары с актуальной ценой указанного типа
        now = timezone.now()
        products_with_price = Product.objects.filter(
            is_active=True,
            prices__price_type=price_type,
            prices__is_active=True,
            prices__start_date__lte=now
        ).filter(
            models.Q(prices__end_date__isnull=True) |
            models.Q(prices__end_date__gte=now)
        ).distinct()

        page = self.paginate_queryset(products_with_price)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(products_with_price, many=True)
        return Response(serializer.data)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer


class PriceTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """API для типов цен"""
    queryset = PriceType.objects.all()
    serializer_class = PriceTypeSerializer


class ProductImageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ProductImage.objects.all().select_related('product')
    serializer_class = ProductImageSerializer

    @action(detail=False, methods=['get'], url_path='by_product/(?P<product_id>[^/.]+)')
    def by_product(self, request, product_id=None):
        images = ProductImage.objects.filter(product_id=product_id).order_by('-is_main', 'id')
        serializer = self.get_serializer(images, many=True, context={'request': request})
        return Response(serializer.data)


