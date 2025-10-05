from django.contrib import admin
from django.db.models import Sum, F
from django.utils.html import format_html

from .models import Orders, OrderItems, DeliveryAddress
from products.models import Product


class OrderItemsInline(admin.TabularInline):
    model = OrderItems
    extra = 1
    autocomplete_fields = ['product', 'warehouse']
    readonly_fields = ('price_per_unit_display', 'total_price_display', 'available_stock')
    fields = ('product', 'warehouse', 'quantity', 'price_per_unit_display', 'total_price_display', 'available_stock')

    @admin.display(description='Цена за ед.')
    def price_per_unit_display(self, obj):
        return f"{obj.price_per_unit:.2f} ₽" if obj.price_per_unit else "-"

    @admin.display(description='Сумма позиции')
    def total_price_display(self, obj):
        return f"{obj.total_price:.2f} ₽" if obj.total_price else "-"

    @admin.display(description='Остаток на складе')
    def available_stock(self, obj):
        if not obj.product:
            return "-"
        stock = getattr(obj.product, 'stock_cache', None)
        if stock is None:
            stock = obj.product.stocks.aggregate(total=Sum('quantity'))['total'] or 0
        color = "green" if stock > 10 else "orange" if stock > 0 else "red"
        return format_html(f'<span style="color:{color};font-weight:600;">{stock}</span>')


@admin.register(Orders)
class OrdersAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status_colored', 'order_sum_display', 'payment_method', 'created_at', 'updated_at')
    list_filter = ('status', 'payment_method', 'created_at')
    search_fields = ('user__username', 'id')
    readonly_fields = ('created_at', 'updated_at', 'order_sum_display')
    inlines = [OrderItemsInline]
    ordering = ('-created_at',)
    actions = ['cancel_orders']

    @admin.display(description='Статус')
    def status_colored(self, obj):
        colors = {
            'new': 'blue',
            'paid': 'green',
            'cancelled': 'red',
            'delivering': 'orange',
            'completed': 'gray',
        }
        color = colors.get(obj.status, 'black')
        return format_html(f'<b style="color:{color};">{obj.get_status_display()}</b>')

    @admin.display(description='Сумма заказа')
    def order_sum_display(self, obj):
        return f"{obj.order_sum:.2f} ₽"

    @admin.action(description='Отменить заказ и вернуть товары на склад')
    def cancel_orders(self, request, queryset):
        for order in queryset:
            if order.status == 'cancelled':
                continue
            for item in order.items.all():
                if item.product and item.warehouse:
                    item.product.stock_cache = F('stock_cache') + item.quantity
                    item.product.save(update_fields=['stock_cache'])
            order.status = 'cancelled'
            order.save(update_fields=['status'])
        self.message_user(request, f"Отменено {queryset.count()} заказов и возвращено на склад.")


@admin.register(OrderItems)
class OrderItemsAdmin(admin.ModelAdmin):
    list_display = ('order', 'product', 'warehouse', 'quantity', 'price_per_unit', 'total_price')
    list_filter = ('warehouse',)
    search_fields = ('product__name', 'order__id')


@admin.register(DeliveryAddress)
class DeliveryAddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'city', 'street', 'house', 'apartment', 'created_at')
    search_fields = ('city', 'street', 'house', 'user__username')
