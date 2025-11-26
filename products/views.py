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

    # -------------------------------------------------------
    # 🔹 Чтение файла (xlsx/csv/json)
    # -------------------------------------------------------
    def parse_file(self, file):
        try:
            if file.name.endswith(".json"):
                return pd.DataFrame(pd.read_json(file))
            try:
                return pd.read_excel(file)
            except Exception:
                return pd.read_csv(file)
        except Exception as e:
            raise ValueError(f"Ошибка чтения файла: {e}")

    # -------------------------------------------------------
    # 🔹 Сам импорт
    # -------------------------------------------------------
    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"detail": "Файл не передан"}, status=400)

        try:
            df = self.parse_file(file)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)

        created, updated = 0, 0
        errors = []

        base_price_type, _ = PriceType.objects.get_or_create(
            code=self.BASE_PRICE_TYPE_CODE,
            defaults={"name": "Базовая цена"}
        )

        for idx, row in df.iterrows():
            try:
                with transaction.atomic():
                    # ---------------------------------------------------
                    # 🔸 Категория
                    # ---------------------------------------------------
                    category_name = row.get("Категория")
                    category = None
                    if category_name:
                        category, _ = Category.objects.get_or_create(
                            name=str(category_name).strip(),
                            defaults={"slug": slugify(category_name)}
                        )

                    # ---------------------------------------------------
                    # 🔸 Теги
                    # ---------------------------------------------------
                    tags_raw = row.get("Теги")
                    tags_list = []
                    if tags_raw:
                        for tag_name in str(tags_raw).split(","):
                            tag_name = tag_name.strip()
                            if not tag_name:
                                continue
                            tag, _ = Tag.objects.get_or_create(
                                name=tag_name,
                                defaults={"slug": slugify(tag_name)}
                            )
                            tags_list.append(tag)

                    # ---------------------------------------------------
                    # 🔸 Единица измерения
                    # ---------------------------------------------------
                    unit_code = row.get("Единица") or "pcs"
                    unit, _ = Unit.objects.get_or_create(
                        code=str(unit_code).strip(),
                        defaults={"name": str(unit_code)}
                    )

                    # ---------------------------------------------------
                    # 🔸 SKU
                    # ---------------------------------------------------
                    raw_sku = row.get("SKU")
                    sku = str(raw_sku).strip() if raw_sku else str(uuid.uuid4())

                    # ---------------------------------------------------
                    # 🔸 Поля товара
                    # ---------------------------------------------------
                    name = row.get("Название") or "Без названия"
                    description = row.get("Описание") or ""
                    weight = int(row.get("Вес") or 0)
                    active = row.get("Активен")
                    is_active = bool(active) if active in [0, 1, True, False] else True

                    origin = row.get("Происхождение") or ""

                    exp_raw = row.get("Срок годности")
                    expiration_date = None
                    if exp_raw:
                        try:
                            expiration_date = pd.to_datetime(exp_raw).date()
                        except:
                            pass

                    product_defaults = {
                        "name": name,
                        "slug": slugify(name)[:50],
                        "description": description,
                        "category": category,
                        "unit": unit,
                        "weight": weight,
                        "is_active": is_active,
                        "origin": origin,
                        "expiration_date": expiration_date,
                    }

                    obj, created_flag = Product.objects.update_or_create(
                        sku=sku, defaults=product_defaults
                    )

                    # Теги
                    if tags_list:
                        obj.tags.set(tags_list)

                    # ---------------------------------------------------
                    # 🔸 Цена
                    # ---------------------------------------------------
                    price_value = row.get("Цена (базовая)")
                    if price_value:
                        Price.objects.update_or_create(
                            product=obj,
                            price_type=base_price_type,
                            defaults={
                                "value": price_value,
                                "start_date": timezone.now(),
                                "is_active": True,
                            },
                        )

                    # ---------------------------------------------------
                    # 🔸 Остатки
                    # ---------------------------------------------------
                    wh_name = row.get("Склад")
                    stock_qty = row.get("Остаток")

                    if wh_name and stock_qty is not None:
                        wh, _ = Warehouse.objects.get_or_create(name=str(wh_name).strip())

                        Stock.objects.update_or_create(
                            product=obj,
                            warehouse=wh,
                            defaults={"quantity": int(stock_qty), "unit": unit},
                        )

                        obj.stock_cache = obj.stocks.aggregate(total=Sum("quantity"))["total"] or 0
                        obj.save()

                    created += created_flag
                    updated += (not created_flag)

            except Exception as e:
                errors.append({"row": int(idx), "error": str(e)})

        return Response(
            {"created": created, "updated": updated, "errors": errors},
            status=200
        )


class ProductExportView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        data = []

        products = Product.objects.select_related(
            "category", "unit"
        ).prefetch_related(
            "tags", "prices", "stocks", "images"
        )

        for p in products:
            prices = [{
                "type": price.price_type.code,
                "value": str(price.value),
                "start_date": price.start_date,
                "end_date": price.end_date,
                "is_active": price.is_active,
            } for price in p.prices.all()]

            stocks = [{
                "warehouse": s.warehouse.name,
                "quantity": s.quantity
            } for s in p.stocks.all()]

            images = [{
                "url": request.build_absolute_uri(img.image.url),
                "is_main": img.is_main
            } for img in p.images.all()]

            data.append({
                "sku": p.sku,
                "name": p.name,
                "description": p.description,
                "category": p.category.name if p.category else None,
                "tags": [t.name for t in p.tags.all()],
                "unit": p.unit.code,
                "origin": p.origin,
                "expiration_date": p.expiration_date,
                "is_active": p.is_active,
                "stock_cache": p.stock_cache,

                "prices": prices,
                "stocks": stocks,
                "images": images,
            })

        return Response(data)


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


