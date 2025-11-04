from decimal import Decimal
from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Sum

from products.models import Product, Warehouse, Stock, Price


class DeliveryAddress(models.Model):
    """Адрес доставки пользователя"""
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='addresses', verbose_name='Пользователь'
    )
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
    address = models.ForeignKey(
        DeliveryAddress, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Адрес доставки'
    )
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='cash', verbose_name='Метод оплаты')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new', verbose_name='Статус')
    order_sum = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Сумма заказа')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'
        ordering = ['-created_at']

    def __str__(self):
        return f"Заказ #{self.id or '—'} ({self.get_status_display()})"

    def recalc_total(self):
        """Пересчитать сумму заказа"""
        total = self.items.aggregate(total=models.Sum('total_price'))['total'] or Decimal('0.00')
        self.order_sum = total
        self.save(update_fields=['order_sum'])
        return total

    @transaction.atomic
    def confirm(self):
        """Подтверждение заказа — списание остатков"""
        if self.status != 'new':
            raise ValidationError("Только новый заказ можно подтвердить.")

        for item in self.items.select_related('product'):
            product = item.product
            qty = item.quantity

            # Проверяем наличие на складе
            stock = Stock.objects.filter(product=product).first()
            if not stock or stock.quantity < qty:
                raise ValidationError(f"Недостаточно товара '{product.name}' на складе!")

            # Списываем остаток
            stock.quantity -= qty
            stock.save()

            # Обновляем кэш
            product.stock_cache = product.stocks.aggregate(total=Sum('quantity'))['total'] or 0
            product.save(update_fields=['stock_cache'])

        self.status = 'confirmed'
        self.save(update_fields=['status'])

    @transaction.atomic
    def cancel(self):
        """Отмена заказа — возврат остатков"""
        if self.status not in ['new', 'confirmed']:
            raise ValidationError("Можно отменить только новый или подтверждённый заказ.")

        for item in self.items.select_related('product'):
            product = item.product
            qty = item.quantity

            stock = Stock.objects.filter(product=product).first()
            if stock:
                stock.quantity += qty
                stock.save()

            # Обновляем кэш
            product.stock_cache = product.stocks.aggregate(total=Sum('quantity'))['total'] or 0
            product.save(update_fields=['stock_cache'])

        self.status = 'cancelled'
        self.save(update_fields=['status'])

    @transaction.atomic
    def update_stock_on_confirm(self):
        """
        Списывает товары со склада при подтверждении заказа.
        Использует блокировку строк, чтобы избежать гонок.
        """
        for item in self.items.select_related('product').select_for_update():
            product = item.product
            quantity = item.quantity

            # Получаем основной склад, например первый
            stock = Stock.objects.filter(product=product).select_for_update().first()
            if not stock or stock.quantity < quantity:
                raise ValueError(f"Недостаточно товара '{product.name}' на складе")

            # Списываем со склада
            stock.quantity -= quantity
            stock.save(update_fields=['quantity'])

            # Обновляем кэш остатка в продукте
            total = product.stocks.aggregate(total=Sum('quantity'))['total'] or 0
            product.stock_cache = total
            product.save(update_fields=['stock_cache'])


class OrderItems(models.Model):
    """Позиции заказа"""
    order = models.ForeignKey('Orders', on_delete=models.CASCADE, related_name='items', verbose_name='Заказ')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='order_items', verbose_name='Товар')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Склад')
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Цена за единицу', editable=False)
    quantity = models.PositiveIntegerField(default=1, verbose_name='Количество')
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Сумма позиции', editable=False)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        verbose_name = 'Позиция заказа'
        verbose_name_plural = 'Позиции заказов'
        ordering = ['id']
        index_together = [('order', 'product')]

    def __str__(self):
        return f"{self.product.name} × {self.quantity}"

    # -----------------------------
    # 🔹 Валидация
    # -----------------------------
    def clean(self):
        if self.quantity <= 0:
            raise ValidationError("Количество должно быть больше нуля.")
        if not self.product:
            raise ValidationError("Не указан товар.")

    # -----------------------------
    # 🔹 Получение актуальной цены
    # -----------------------------
    def get_current_price(self):
        """Возвращает актуальную цену из таблицы Prices"""
        now = timezone.now()
        price_obj = (
            Prices.objects.filter(
                product=self.product,
                start_date__lte=now
            )
            .filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=now))
            .order_by('-start_date')
            .first()
        )
        return price_obj.value if price_obj else getattr(self.product, 'price', 0)

    # -----------------------------
    # 🔹 Сохранение
    # -----------------------------
    @transaction.atomic
    def save(self, *args, **kwargs):
        # 1️⃣ Устанавливаем цену, если не задана
        if not self.price_per_unit:
            self.price_per_unit = self.get_current_price()

        # 2️⃣ Пересчитываем сумму позиции
        self.total_price = (self.price_per_unit or 0) * self.quantity

        # 3️⃣ Сохраняем саму позицию
        super().save(*args, **kwargs)

        # 4️⃣ Пересчитываем общую сумму заказа
        if self.order_id:
            total = self.order.items.aggregate(total=Sum('total_price'))['total'] or 0
            self.order.order_sum = total
            self.order.save(update_fields=['order_sum'])

        # 5️⃣ Обновляем кеш остатка (чтобы в админке показывало верно)
        total_stock = self.product.stocks.aggregate(total=Sum('quantity'))['total'] or 0
        self.product.stock_cache = total_stock
        self.product.save(update_fields=['stock_cache'])
