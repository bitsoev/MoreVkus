from rest_framework import serializers
from .models import Product, Category, Tag, ProductImage, Unit


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


class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    tags = serializers.StringRelatedField(many=True)
    category = serializers.StringRelatedField()
    category_id = serializers.PrimaryKeyRelatedField(source='category', read_only=True)

    unit = serializers.StringRelatedField()
    unit_id = serializers.PrimaryKeyRelatedField(source='unit', read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'sku', 'name', 'description',
            'unit', 'unit_id', 'stock_cache', 'is_active', 'is_featured',
            'origin', 'expiration_date', 'category', 'category_id',
            'tags', 'images', 'ms_uuid', 'synced_at', 'changed_locally'
        ]
        read_only_fields = ('synced_at', 'changed_locally', 'stock_cache')


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'ms_uuid']
