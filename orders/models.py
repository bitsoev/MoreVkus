from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils import timezone

from products.models import Product, Warehouse, Stock


class DeliveryAddress(models.Model):
    """Адрес доставки"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses', verbose_name='Пользователь')
    city = models.CharField(max_length=100, verbose_name='Город')
    street = models.CharField(max_length=255, verbose_name='Улица')
    house = models.CharField(max_length=20, verbose_name='Дом')
    apartment = models.CharField(max_length=20, blank=True, null=True, verbose_name='Квартира')
    comment = models.TextField(blank=True, null=True, verbose_name='Комментарий')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Адрес доставки'
        verbose_name_plural = 'Адреса доставки'

    def __str__(self):
        return f"{self.city}, {self.street} {self.house}"


class Orders(models.Model):
    """Основная модель заказа"""

    STATUS_CHOICES = [
        ('new', 'Новый'),
        ('confirmed', 'Подтверждён'),
        ('shipped', 'Отправлен'),
        ('delivered', 'Доставлен'),
        ('cancelled', 'Отменён'),
    ]

    PAYMENT_CHOICES = [
        ('cash', 'Наличные'),
        ('card', 'Карта'),
        ('sbp', 'СБП'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders', verbose_name='Пользователь')
    address = models.ForeignKey(DeliveryAddress, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Адрес доставки')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='cash', verbose_name='Метод оплаты')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new', verbose_name='Статус')
    order_sum = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Сумма заказа')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'
        ordering = ['-created_at']

    def __str__(self):
        return f"Заказ #{self.id} ({self.get_status_display()})"

    @transaction.atomic
    def update_stock_on_confirm(self):
        """Уменьшает остатки товаров при подтверждении заказа"""
        for item in self.items.select_related('product'):
            product = item.product
            quantity = item.quantity

            stock = Stock.objects.filter(product=product).first()
            if not stock or stock.quantity < quantity:
                raise ValueError(f"Недостаточно товара '{product.name}' на складе")

            stock.quantity -= quantity
            stock.save()

            # обновляем кэш остатка в продукте
            total = product.stocks.aggregate(total=models.Sum('quantity'))['total'] or 0
            product.stock_cache = total
            product.save(update_fields=['stock_cache'])

    @transaction.atomic
    def restore_stock_on_cancel(self):
        """Восстанавливает остатки при отмене заказа"""
        for item in self.items.select_related('product'):
            product = item.product
            quantity = item.quantity

            stock = Stock.objects.filter(product=product).first()
            if stock:
                stock.quantity += quantity
                stock.save()

            # обновляем кэш остатка
            total = product.stocks.aggregate(total=models.Sum('quantity'))['total'] or 0
            product.stock_cache = total
            product.save(update_fields=['stock_cache'])


class OrderItems(models.Model):
    """Позиции товаров в заказе"""
    order = models.ForeignKey(Orders, on_delete=models.CASCADE, related_name='items', verbose_name='Заказ')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='order_items', verbose_name='Товар')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Склад')
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Цена за единицу')
    quantity = models.PositiveIntegerField(verbose_name='Количество')
    total_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Сумма')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        verbose_name = 'Позиция заказа'
        verbose_name_plural = 'Позиции заказов'

    def __str__(self):
        return f"{self.product.name} × {self.quantity}"

    def save(self, *args, **kwargs):
        """Автоматически пересчитывает total_price при сохранении"""
        if not self.total_price or self.total_price == 0:
            self.total_price = self.price_per_unit * self.quantity
        super().save(*args, **kwargs)
