from django.db import models

from catalog.models import Product
from django.contrib.auth.models import User

from django.db import models
from django.conf import settings
from products.models import Product


class DeliveryAddress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    city = models.CharField(max_length=255)
    street = models.CharField(max_length=255)
    house = models.CharField(max_length=50)
    apartment = models.CharField(max_length=50, blank=True)
    comment = models.TextField(blank=True)


class Orders(models.Model):
    PAYMENT_CHOICES = [
        ('card', 'Картой онлайн'),
        ('cash', 'Наличными при получении'),
        ('sbp', 'СБП'),
    ]
    STATUS_CHOICES = [
        ('new', 'Новый'),
        ('confirmed', 'Подтвержден'),
        ('packing', 'Собирается'),
        ('delivery', 'Передан в доставку'),
        ('done', 'Доставлен'),
        ('cancelled', 'Отменён'),
    ]
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING, related_name='customer_order')
    created_dttm = models.DateTimeField(auto_now_add=True)
    update_dttm = models.DateTimeField(auto_now=True)
    order_sum = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(choices=STATUS_CHOICES, default='new')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='new')
    address = models.ForeignKey(DeliveryAddress, on_delete=models.SET_NULL, null=True)

    def save(self, *args, **kwargs):
        super(Orders, self).save(*args, **kwargs)
        order_items = OrderItems.objects.filter(order_id=self)
        self.order_sum = sum(item.total_price for item in order_items)
        super(Orders, self).save(update_fields=['order_sum'])

    def __str__(self):
        return f'Заказ №: {self.id} | Клиент:{self.user.username} | Дата:{self.created_dttm.strftime("%Y-%m-%d")} | Сумма:{self.order_sum}'

    def get_order_items(self):
        return OrderItems.objects.filter(id=self)


class OrderItems(models.Model):
    order = models.ForeignKey(Orders, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.DO_NOTHING)
    quantity = models.DecimalField(max_digits=10, default=0, decimal_places=3)
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f'Заказ №: {self.order.id} | Позиция: {self.product.name} | Колличесвто: {self.quantity} | Сумма: {self.total_price}'

    def save(self, *args, **kwargs):
        self.price_per_unit = self.product.price
        self.total_price = self.price_per_unit * self.quantity
        super(OrderItems,self).save(*args, **kwargs)

