from django.contrib import admin
from django.utils.text import slugify
from django.utils.html import format_html
from django.db.models import Sum
from django.utils import timezone

from import_export.admin import ImportExportModelAdmin
from import_export import resources, fields as imp_fields
from import_export.widgets import ForeignKeyWidget, ManyToManyWidget

from .models import (
    Category, Tag, Unit, Product, ProductImage,
    Warehouse, Stock, PriceType, Price
)
from .admin_resources import ProductResource, StockResource, PriceResource


# -------------------- Inlines --------------------

class PriceInline(admin.TabularInline):
    model = Price
    extra = 0
    fields = ('price_type', 'value', 'is_active', 'priority', 'start_date', 'end_date')
    ordering = ('-is_active', '-priority', '-start_date')
    autocomplete_fields = ['price_type']


class StockInline(admin.TabularInline):
    model = Stock
    extra = 1
    fields = ('warehouse', 'quantity', 'unit', 'updated_at')
    readonly_fields = ('updated_at',)
    autocomplete_fields = ['warehouse', 'unit']


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    readonly_fields = ('image_preview',)
    fields = ('image', 'alt_text', 'is_main', 'image_preview')

    def image_preview(self, obj):
        if not obj or not obj.image:
            return ""
        return format_html('<img src="{}" height="50" />', obj.image.url)
    image_preview.short_description = 'Превью'


# -------------------- Product Admin --------------------

@admin.register(Product)
class ProductAdmin(ImportExportModelAdmin):
    resource_class = ProductResource
    list_display = (
        'name', 'category', 'unit', 'stock_status',
        'sku', 'stock_cache', 'is_active', 'is_featured'
    )
    list_filter = ('category', 'tags', 'is_active', 'is_featured', 'unit')
    search_fields = ('name', 'description', 'sku')
    list_editable = ('is_active', 'is_featured')
    filter_horizontal = ('tags',)
    readonly_fields = ('synced_at',)
    inlines = [PriceInline, StockInline, ProductImageInline]
    actions = ['recalculate_stock_cache']

    @admin.display(description='Остаток')
    def stock_status(self, obj):
        total = obj.stocks.aggregate(total=Sum('quantity'))['total'] or 0
        if total > 10:
            status = '✅ В наличии'
        elif total > 0:
            status = '⚠️ Мало'
        else:
            status = '❌ Нет'
        return f"{status} ({total})"

    @admin.display(description='Остаток (кэш)')
    def stock_cache(self, obj):
        return obj.stock_cache

    @admin.action(description='Пересчитать stock_cache по выбранным товарам')
    def recalculate_stock_cache(self, request, queryset):
        for p in queryset:
            total = p.stocks.aggregate(total=Sum('quantity'))['total'] or 0
            p.stock_cache = total
            p.save(update_fields=['stock_cache'])
        self.message_user(request, f'Пересчитано для {queryset.count()} товаров.')


# -------------------- ProductImage Admin --------------------

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'is_main', 'image_preview')
    readonly_fields = ('image_preview',)

    def image_preview(self, obj):
        if not obj or not obj.image:
            return ""
        return format_html('<img src="{}" height="50" />', obj.image.url)
    image_preview.short_description = 'Превью'


# -------------------- Category / Tag / Unit / Warehouse --------------------

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'product_count', 'ms_uuid')
    prepopulated_fields = {'slug': ('name',)}

    @admin.display(description='Товаров')
    def product_count(self, obj):
        return obj.products.count()


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'ms_uuid')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    search_fields = ['name']
    list_display = ('code', 'name', 'ms_uuid')


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('name', 'ms_uuid')
    search_fields = ('name', 'ms_uuid')


@admin.register(Stock)
class StockAdmin(ImportExportModelAdmin):
    resource_class = StockResource
    list_display = ('product', 'warehouse', 'quantity', 'unit', 'updated_at')
    list_filter = ('warehouse',)
    search_fields = ('product__name', 'warehouse__name')


# -------------------- PriceType / Price Admin --------------------

@admin.register(PriceType)
class PriceTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'ms_uuid')
    search_fields = ('name',)


@admin.register(Price)
class PriceAdmin(ImportExportModelAdmin):
    resource_class = PriceResource
    list_display = (
        'product_link', 'price_type', 'value_display',
        'is_active_colored', 'start_date', 'end_date', 'priority', 'updated_at'
    )
    list_filter = (
        'price_type',
        'is_active',
        ('start_date', admin.DateFieldListFilter),
        ('end_date', admin.DateFieldListFilter),
    )
    search_fields = ('product__name', 'price_type__name')
    autocomplete_fields = ['product', 'price_type']
    readonly_fields = ('updated_at',)
    ordering = ('-is_active', '-priority', '-start_date')
    actions = ['activate_selected', 'deactivate_selected']

    @admin.display(description='Товар')
    def product_link(self, obj):
        url = f"/admin/products/product/{obj.product.id}/change/"
        return format_html(f'<a href="{url}" style="font-weight:500;">{obj.product.name}</a>')

    @admin.display(description='Цена')
    def value_display(self, obj):
        color = '#27ae60' if obj.is_active else '#bdc3c7'
        return format_html(f'<b style="color:{color};">{obj.value:.2f} ₽</b>')

    @admin.display(description='Активна')
    def is_active_colored(self, obj):
        now = timezone.now()
        current = (
            obj.is_active
            and obj.start_date <= now
            and (obj.end_date is None or obj.end_date >= now)
        )
        color = '#2ecc71' if current else '#e74c3c'
        return format_html(f'<b style="color:{color};">{"Да" if current else "Нет"}</b>')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Деактивируем другие активные цены того же типа для продукта
        if obj.is_active:
            Price.objects.filter(
                product=obj.product,
                price_type=obj.price_type
            ).exclude(pk=obj.pk).update(is_active=False)

    @admin.action(description='Активировать выбранные')
    def activate_selected(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Активировано {updated} цен.')

    @admin.action(description='Деактивировать выбранные')
    def deactivate_selected(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Деактивировано {updated} цен.')
