from rest_framework import serializers
from .models import Product, Category, Tag, ProductImage


class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text']  # product убрал

    def get_image(self, obj):
        return obj.image.url


class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    tags = serializers.StringRelatedField(many=True)
    category = serializers.StringRelatedField()
    category_id = serializers.PrimaryKeyRelatedField(
        source='category',
        read_only=True
    )

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'price',
            'weight', 'stock', 'category', 'category_id',
            'tags', 'images'
        ]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug']
