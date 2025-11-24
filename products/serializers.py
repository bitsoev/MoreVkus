from django.utils import timezone
from rest_framework import serializers
from .models import Product, Category, Tag, ProductImage, Unit, PriceType, Price
from django.db import models


class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text', 'is_main']

    def get_image(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        url = obj.image.url
        if request:
            return request.build_absolute_uri(url)
        return url


class ProductPriceSerializer(serializers.ModelSerializer):
    """Сериализатор для цен товара"""
    price_type = serializers.StringRelatedField()
    price_type_code = serializers.CharField(source='price_type.code')

    class Meta:
        model = Price
        fields = [
            'price_type', 'price_type_code', 'value',
            'start_date', 'end_date', 'is_active'
        ]


class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    tags = serializers.StringRelatedField(many=True)
    category = serializers.StringRelatedField()
    category_id = serializers.PrimaryKeyRelatedField(source='category', read_only=True)

    unit = serializers.StringRelatedField()
    unit_id = serializers.PrimaryKeyRelatedField(source='unit', read_only=True)

    # Добавляем поля для цен
    current_price = serializers.SerializerMethodField()
    all_prices = serializers.SerializerMethodField()
    price_types_available = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'sku', 'name', 'description',
            'unit', 'unit_id', 'stock_cache', 'is_active', 'is_featured',
            'origin', 'expiration_date', 'category', 'category_id',
            'tags', 'images', 'ms_uuid', 'synced_at', 'changed_locally',
            'current_price', 'all_prices', 'price_types_available'  # Добавленные поля
        ]
        read_only_fields = ('synced_at', 'changed_locally', 'stock_cache')

    def get_current_price(self, obj):
        """Получить основную актуальную цену"""
        price = Price.get_current_price(obj)
        if price:
            return {
                'value': str(price.value),
                'price_type': price.price_type.name,
                'price_type_code': price.price_type.code,
                'currency': 'RUB'
            }
        return None

    def get_all_prices(self, obj):
        """Получить все актуальные цены по типам"""
        now = timezone.now()
        prices = obj.prices.filter(
            is_active=True,
            start_date__lte=now
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=now)
        ).select_related('price_type')

        return ProductPriceSerializer(prices, many=True).data

    def get_price_types_available(self, obj):
        """Получить доступные типы цен для товара"""
        now = timezone.now()
        price_types = PriceType.objects.filter(
            prices__product=obj,
            prices__is_active=True,
            prices__start_date__lte=now
        ).filter(
            models.Q(prices__end_date__isnull=True) |
            models.Q(prices__end_date__gte=now)
        ).distinct()

        return [{'code': pt.code, 'name': pt.name} for pt in price_types]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'ms_uuid']


class PriceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceType
        fields = ['id', 'name', 'code', 'ms_uuid', 'description']



