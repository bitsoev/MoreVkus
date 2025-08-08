import datetime
from django.db import models
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class InStockManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(in_stock=True)


class Product(models.Model):
    category = models.ForeignKey(Category, related_name='products', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    in_stock = models.BooleanField(default=True)
    product_count = models.FloatField(default=0)

    objects = models.Manager()
    instock = InStockManager()

    def __str__(self):
        return self.name
