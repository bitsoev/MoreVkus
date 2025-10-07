from django.contrib import admin
from django.utils.text import slugify
from django.utils.html import format_html
from django.db.models import Sum

from import_export import resources
from import_export import fields as imp_fields
from import_export.admin import ImportExportModelAdmin
from import_export.widgets import ForeignKeyWidget, ManyToManyWidget

from .models import (
    Category, Tag, Unit, Product, ProductImage,
    Warehouse, Stock, PriceType, Price
)


# -------------------- Inlines --------------------

class StockInline(admin.TabularInline):
    model = Stock
    extra = 1  # сколько пустых строк для нового склада показывать


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


# -------------------- Product Import/Export --------------------

class ProductResource(resources.ModelResource):
    category = imp_fields.Field(
        column_name='Категория',
        attribute='category',
        widget=ForeignKeyWidget(Category, 'name')
    )

    tags = imp_fields.Field(
        column_name='Теги',
        attribute='tags',
        widget=ManyToManyWidget(Tag, field='name', separator=',')
    )

    unit = imp_fields.Field(
        column_name='Единица',
        attribute='unit',
        widget=ForeignKeyWidget(Unit, 'code')
    )

    sku = imp_fields.Field(column_name='SKU', attribute='sku')
    ms_uuid = imp_fields.Field(column_name='MS UUID', attribute='ms_uuid')
    expiration_date = imp_fields.Field(column_name='Срок годности', attribute='expiration_date')

    stock_quantity = imp_fields.Field(
        column_name='Количество',
        attribute='stock_quantity',  # виртуальное поле для импорта
    )

    class Meta:
        model = Product
        fields = (
            'id', 'sku', 'name', 'category', 'tags', 'price', 'discount_price',
            'weight', 'unit', 'stock_cache', 'is_active', 'is_featured',
            'origin', 'expiration_date', 'ms_uuid'
        )
        export_order = fields
        import_id_fields = ('sku',)
        skip_unchanged = True
        report_skipped = True

    def dehydrate_tags(self, product):
        return ', '.join(tag.name for tag in product.tags.all())

    def before_import_row(self, row, **kwargs):
        raw_cat = row.get('Категория') or ''
        if raw_cat and not Category.objects.filter(name=raw_cat).exists():
            Category.objects.get_or_create(name=raw_cat, defaults={'slug': slugify(raw_cat)})

        raw_tags = row.get('Теги') or ''
        if raw_tags:
            tag_names = [t.strip() for t in raw_tags.split(',') if t.strip()]
            for name in tag_names:
                Tag.objects.get_or_create(name=name, defaults={'slug': slugify(name)})

        raw_unit = row.get('Единица') or ''
        if raw_unit and not Unit.objects.filter(code=raw_unit).exists():
            Unit.objects.get_or_create(code=raw_unit, defaults={'name': raw_unit})

    def after_save_instance(self, instance, **kwargs):
        """
        После сохранения Product создаем/обновляем Stock на основном складе.
        Ожидается колонка 'Количество' в Excel.
        """
        from products.models import Warehouse, Stock

        row = kwargs.get('row')
        if not row:
            try:
                row = self.get_row_from_instance(instance)
            except Exception:
                return

        quantity = row.get('Количество')
        if not quantity:
            return

        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            return

        warehouse, _ = Warehouse.objects.get_or_create(name='Основной склад')
        Stock.objects.update_or_create(
            product=instance,
            warehouse=warehouse,
            defaults={'quantity': quantity}
        )


# -------------------- Product Admin --------------------

@admin.register(Product)
class ProductAdmin(ImportExportModelAdmin):
    resource_class = ProductResource

    list_display = (
        'sku', 'name', 'category', 'price', 'discount_price',
        'weight', 'unit', 'stock_status', 'stock_cache', 'is_active', 'is_featured'
    )
    list_filter = ('category', 'tags', 'is_active', 'is_featured', 'unit')
    search_fields = ('name', 'description', 'sku')
    list_editable = ('price', 'discount_price', 'weight', 'is_active', 'is_featured')
    filter_horizontal = ('tags',)

    readonly_fields = ('synced_at',)

    inlines = [StockInline, ProductImageInline]

    actions = ['recalculate_stock_cache']

    @admin.display(description='Остаток')
    def stock_status(self, obj):
        total = obj.stocks.aggregate(total=Sum('quantity'))['total'] or 0
        if total > 10:
            status = 'В наличии'
        elif total > 0:
            status = 'Мало'
        else:
            status = 'Нет в наличии'
        return f"{status} ({total})"

    @admin.display(description='Остаток (кратко)')
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
    list_display = ('code', 'name', 'ms_uuid')


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('name', 'ms_uuid')
    search_fields = ('name', 'ms_uuid')


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ('product', 'warehouse', 'quantity', 'updated_at')
    list_filter = ('warehouse',)


@admin.register(PriceType)
class PriceTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'ms_uuid')


@admin.register(Price)
class PriceAdmin(admin.ModelAdmin):
    list_display = ('product', 'price_type', 'value', 'updated_at')
    list_filter = ('price_type',)
