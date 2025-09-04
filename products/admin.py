from django.contrib import admin
from django.utils.text import slugify
from import_export import resources, fields
from import_export.admin import ImportExportModelAdmin
from import_export.widgets import ForeignKeyWidget, ManyToManyWidget
from import_export.formats import base_formats
from .models import Category, Tag, Product, ProductImage

class ProductResource(resources.ModelResource):
    category = fields.Field(
        attribute='category',
        column_name='Категория',
        widget=ForeignKeyWidget(Category, 'name')
    )
    
    tags = fields.Field(
        attribute='tags',
        column_name='Теги',
        widget=ManyToManyWidget(Tag, field='name', separator=',')
    )

    class Meta:
        model = Product
        fields = ('id', 'name', 'category', 'tags', 'price', 'weight', 'description', 'stock', 'is_active')
        export_order = fields
        import_id_fields = ['id']
        skip_unchanged = True

    def dehydrate_tags(self, product):
        """Форматирование тегов для экспорта"""
        return ', '.join(tag.name for tag in product.tags.all())

    def before_import_row(self, row, **kwargs):
        """Подготовка данных перед импортом"""
        # Обработка категории
        category_name = row.get('Категория')
        if category_name:
            category, _ = Category.objects.get_or_create(
                name=category_name,
                defaults={'slug': slugify(category_name)}
            )
            row['category'] = category.id
        
        # Обработка тегов
        tags_str = row.get('Теги', '')
        if tags_str:
            tag_names = [name.strip() for name in tags_str.split(',') if name.strip()]
            tags = []
            for name in tag_names:
                tag, _ = Tag.objects.get_or_create(
                    name=name,
                    defaults={'slug': slugify(name)}
                )
                tags.append(tag)
            row['tags'] = tags

@admin.register(Product)
class ProductAdmin(ImportExportModelAdmin):
    resource_class = ProductResource
    list_display = ('name', 'category', 'price', 'weight', 'stock_status')
    list_filter = ('category', 'tags', 'is_active')
    search_fields = ('name', 'description')
    list_editable = ('price', 'weight')
    filter_horizontal = ('tags',)
    
    def get_export_formats(self):
        """Форматы экспорта (XLSX и CSV)"""
        formats = (
            base_formats.XLSX,
            base_formats.CSV,
        )
        return [f for f in formats if f().can_export()]
    
    @admin.display(description='Остаток')
    def stock_status(self, obj):
        if obj.stock > 10:
            return 'В наличии'
        elif obj.stock > 0:
            return 'Мало'
        return 'Нет в наличии'

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'product_count')
    prepopulated_fields = {'slug': ('name',)}
    
    @admin.display(description='Товаров')
    def product_count(self, obj):
        return obj.products.count()

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'image_preview')
    readonly_fields = ('image_preview',)
    
    def image_preview(self, obj):
        from django.utils.html import format_html
        return format_html(f'<img src="{obj.image.url}" height="50" />')
