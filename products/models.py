import uuid

from django.db import models
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)
    ms_uuid = models.CharField(max_length=36, null=True, blank=True, unique=True)

    def __str__(self):
        return self.name


class Tag(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    ms_uuid = models.CharField(max_length=36, null=True, blank=True, unique=True)

    def __str__(self):
        return self.name


class Unit(models.Model):
    code = models.CharField(max_length=10, unique=True)  # g, kg, pcs, l
    name = models.CharField(max_length=50)
    ms_uuid = models.CharField(max_length=36, null=True, blank=True, unique=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)

    category = models.ForeignKey('products.Category', on_delete=models.CASCADE, related_name='products')
    tags = models.ManyToManyField('products.Tag', blank=True)

    sku = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    weight = models.PositiveIntegerField(help_text="в граммах")
    #unit = models.ForeignKey('products.Unit', on_delete=models.SET_NULL, null=True, blank=True)
    unit = models.ForeignKey('products.Unit', on_delete=models.PROTECT, default=1)

    # Кеш общего остатка (для быстрого фронта)
    stock_cache = models.IntegerField(default=0)

    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    origin = models.CharField(max_length=255, blank=True)
    expiration_date = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Синхронизация с МС
    synced_at = models.DateTimeField(null=True, blank=True)
    changed_locally = models.BooleanField(default=False)
    ms_uuid = models.CharField(max_length=36, null=True, blank=True, unique=True)

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='product_images/')
    alt_text = models.CharField(max_length=255, blank=True)
    is_main = models.BooleanField(default=False)

    def __str__(self):
        return f"Image for {self.product.name}"


class Warehouse(models.Model):
    name = models.CharField(max_length=255)
    ms_uuid = models.CharField(max_length=36, unique=True, null=True, blank=True)

    def __str__(self):
        return self.name


class Stock(models.Model):
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='stocks')
    warehouse = models.ForeignKey('products.Warehouse', on_delete=models.CASCADE, related_name='stocks')
    quantity = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('product', 'warehouse')

    def __str__(self):
        return f"{self.product.name} @ {self.warehouse.name}: {self.quantity}"


class PriceType(models.Model):
    name = models.CharField(max_length=255)
    ms_uuid = models.CharField(max_length=36, unique=True, null=True, blank=True)

    def __str__(self):
        return self.name


class Price(models.Model):
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='prices')
    price_type = models.ForeignKey('products.PriceType', on_delete=models.CASCADE, related_name='prices')
    value = models.DecimalField(max_digits=10, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('product', 'price_type')

    def __str__(self):
        return f"{self.product.name} - {self.price_type.name}: {self.value}"
