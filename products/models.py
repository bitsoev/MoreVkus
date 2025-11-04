import uuid

from django.core.exceptions import ValidationError
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
    unit = models.ForeignKey('products.Unit', on_delete=models.PROTECT, default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('product', 'warehouse')

    def __str__(self):
        return f"{self.product.name} @ {self.warehouse.name}: {self.quantity}"


class PriceType(models.Model):
    """Тип цены — розничная, оптовая, акционная и т.д."""
    name = models.CharField(max_length=50, unique=True, verbose_name='Тип цены')
    ms_uuid = models.SlugField(max_length=50, unique=True, verbose_name='Код')
    description = models.TextField(blank=True, verbose_name='Описание')

    class Meta:
        verbose_name = 'Тип цены'
        verbose_name_plural = 'Типы цен'

    def __str__(self):
        return self.name


class Price(models.Model):
    """Модель для хранения истории и типов цен товара"""

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='prices',
        verbose_name='Товар'
    )

    price_type = models.ForeignKey(
        'products.PriceType',
        on_delete=models.CASCADE,
        related_name='prices',
        verbose_name='Тип цены'
    )

    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Цена'
    )

    start_date = models.DateTimeField(
        default=timezone.now,
        verbose_name='Дата начала действия'
    )

    end_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Дата окончания действия'
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name='Активна'
    )

    priority = models.PositiveSmallIntegerField(
        default=0,
        help_text='Чем выше значение, тем приоритетнее цена при пересечении периодов.'
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Цена'
        verbose_name_plural = 'Цены'
        ordering = ['-priority', '-start_date']
        indexes = [
            models.Index(fields=['product', 'price_type']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.product.name} — {self.price_type.name}: {self.value} ₽"

    def clean(self):
        if self.end_date and self.end_date <= self.start_date:
            raise ValidationError("Дата окончания должна быть позже даты начала.")
        if self.value <= 0:
            raise ValidationError("Цена должна быть больше нуля.")

    def is_current(self):
        """Проверяет, активна ли цена на текущую дату"""
        now = timezone.now()
        return (
            self.is_active
            and self.start_date <= now
            and (self.end_date is None or self.end_date >= now)
        )

    @classmethod
    def get_current_price(cls, product, price_type=None):
        """Возвращает актуальную цену для товара (учитывает приоритет, даты и тип цены)"""
        now = timezone.now()
        qs = cls.objects.filter(
            product=product,
            is_active=True,
            start_date__lte=now
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=now)
        )

        if price_type:
            qs = qs.filter(price_type=price_type)

        return qs.order_by('-priority', '-start_date').first()