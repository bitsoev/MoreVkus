from rest_framework import serializers
from .models import Product, Category, Tag, ProductImage


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['image', 'alt_text']


class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    tags = serializers.StringRelatedField(many=True)
    category = serializers.StringRelatedField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'description', 'price', 'weight', 'stock', 'category', 'tags', 'images']


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug']
