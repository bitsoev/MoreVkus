from django.contrib import admin
from .models import OrderItems, Orders, DeliveryAddress

admin.site.register(Orders)
admin.site.register(OrderItems)
admin.site.register(DeliveryAddress)