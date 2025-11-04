from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Sum
from django.utils.html import format_html

from .models import Orders, OrderItems, DeliveryAddress
from products.models import Stock


# ========================= INLINE: Order Items =========================

class OrderItemsInline(admin.TabularInline):
    model = OrderItems
    extra = 0
    autocomplete_fields = ['product', 'warehouse']
    readonly_fields = (
        'price_per_unit_display',
        'total_price_display',
        'available_stock_display',
    )
    fields = (
        'product',
        'warehouse',
        'quantity',
        'price_per_unit_display',
        'total_price_display',
        'available_stock_display',
    )

    @admin.display(description='Цена за ед.')
    def price_per_unit_display(self, obj):
        return f"{obj.price_per_unit:.2f} ₽" if obj.price_per_unit else "-"

    @admin.display(description='Сумма позиции')
    def total_price_display(self, obj):
        return f"{obj.total_price:.2f} ₽" if obj.total_price else "-"

    @admin.display(description='Остаток на складе')
    def available_stock_display(self, obj):
        if not obj.product:
            return "-"
        total = obj.product.stocks.aggregate(total=Sum('quantity'))['total'] or 0
        color = "green" if total > 10 else "orange" if total > 0 else "red"
        return format_html(f'<b style="color:{color};">{total}</b>')


# ========================= ADMIN: Orders =========================

@admin.register(Orders)
class OrdersAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'status_colored', 'order_sum_display',
        'payment_method', 'address_display', 'created_at', 'updated_at'
    )
    list_filter = ('status', 'payment_method', 'created_at')
    search_fields = ('user__username', 'id')
    readonly_fields = ('created_at', 'updated_at', 'order_sum_display')
    inlines = [OrderItemsInline]
    ordering = ('-created_at',)
    actions = ['confirm_orders', 'mark_as_shipped', 'mark_as_delivered', 'cancel_orders']
    save_on_top = True

    # ----------- Display helpers -----------

    @admin.display(description='Статус')
    def status_colored(self, obj):
        colors = {
            'new': '#3498db',         # синий
            'confirmed': '#2ecc71',   # зеленый
            'shipped': '#f39c12',     # оранжевый
            'delivered': '#7f8c8d',   # серый
            'cancelled': '#e74c3c',   # красный
        }
        color = colors.get(obj.status, 'black')
        return format_html(f'<b style="color:{color};">{obj.get_status_display()}</b>')

    @admin.display(description='Сумма заказа')
    def order_sum_display(self, obj):
        return f"{obj.order_sum:.2f} ₽"

    @admin.display(description='Адрес доставки')
    def address_display(self, obj):
        return str(obj.address) if obj.address else "—"

    # ========================= ACTIONS =========================

    @admin.action(description='✅ Подтвердить заказ (списать остатки)')
    @transaction.atomic
    def confirm_orders(self, request, queryset):
        confirmed = 0
        for order in queryset.prefetch_related('items__product'):
            if order.status != 'new':
                continue
            try:
                order.update_stock_on_confirm()
                order.status = 'confirmed'
                order.save(update_fields=['status'])
                confirmed += 1
            except Exception as e:
                self.message_user(
                    request,
                    f"Ошибка при подтверждении заказа #{order.id}: {e}",
                    messages.ERROR
                )
        self.message_user(request, f"Подтверждено {confirmed} заказ(ов)", messages.SUCCESS)

    @admin.action(description='📦 Отметить как отправленные')
    def mark_as_shipped(self, request, queryset):
        updated = queryset.filter(status='confirmed').update(status='shipped')
        self.message_user(request, f"Отмечено {updated} заказ(ов) как отправленные", messages.SUCCESS)

    @admin.action(description='🚚 Отметить как доставленные')
    def mark_as_delivered(self, request, queryset):
        updated = queryset.filter(status='shipped').update(status='delivered')
        self.message_user(request, f"Отмечено {updated} заказ(ов) как доставленные", messages.SUCCESS)

    @admin.action(description='❌ Отменить заказы и вернуть товары на склад')
    @transaction.atomic
    def cancel_orders(self, request, queryset):
        cancelled = 0
        for order in queryset.prefetch_related('items__product'):
            if order.status in ['cancelled', 'delivered']:
                continue
            try:
                order.restore_stock_on_cancel()
                order.status = 'cancelled'
                order.save(update_fields=['status'])
                cancelled += 1
            except Exception as e:
                self.message_user(
                    request,
                    f"Ошибка при отмене заказа #{order.id}: {e}",
                    messages.ERROR
                )
        self.message_user(request, f"Отменено {cancelled} заказ(ов)", messages.SUCCESS)

    # ========================= SAVE LOGIC =========================

    @transaction.atomic
    def save_related(self, request, form, formsets, change):
        """
        После сохранения позиций:
        - пересчитывает сумму
        - не списывает остатки повторно
        """
        super().save_related(request, form, formsets, change)

        order = form.instance
        total_sum = sum(item.total_price for item in order.items.all())
        order.order_sum = total_sum
        order.save(update_fields=['order_sum'])


# ========================= ADMIN: OrderItems =========================

@admin.register(OrderItems)
class OrderItemsAdmin(admin.ModelAdmin):
    list_display = ('order', 'product', 'warehouse', 'quantity', 'price_per_unit', 'total_price')
    list_filter = ('warehouse',)
    search_fields = ('product__name', 'order__id')


# ========================= ADMIN: DeliveryAddress =========================

@admin.register(DeliveryAddress)
class DeliveryAddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'city', 'street', 'house', 'apartment', 'created_at')
    search_fields = ('city', 'street', 'house', 'user__username')
