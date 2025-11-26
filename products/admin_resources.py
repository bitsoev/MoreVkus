from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget, ManyToManyWidget
from .models import Product, Category, Tag, Unit, Warehouse, Stock, Price, PriceType


class ProductResource(resources.ModelResource):
    category = fields.Field(
        attribute="category",
        column_name="category",
        widget=ForeignKeyWidget(Category, "slug"),
    )

    tags = fields.Field(
        attribute="tags",
        column_name="tags",
        widget=ManyToManyWidget(Tag, "slug"),
    )

    unit = fields.Field(
        attribute="unit",
        column_name="unit",
        widget=ForeignKeyWidget(Unit, "code"),
    )

    class Meta:
        model = Product
        import_id_fields = ("sku",)
        fields = (
            "sku",
            "name",
            "slug",
            "description",
            "category",
            "tags",
            "unit",
            "stock_cache",
            "is_active",
            "is_featured",
            "origin",
            "expiration_date",
            "ms_uuid",
        )


class StockResource(resources.ModelResource):
    product = fields.Field(
        attribute="product",
        column_name="product",
        widget=ForeignKeyWidget(Product, "sku"),
    )
    warehouse = fields.Field(
        attribute="warehouse",
        column_name="warehouse",
        widget=ForeignKeyWidget(Warehouse, "name"),
    )
    unit = fields.Field(
        attribute="unit",
        column_name="unit",
        widget=ForeignKeyWidget(Unit, "code"),
    )

    class Meta:
        model = Stock
        import_id_fields = ("product", "warehouse")
        fields = ("product", "warehouse", "quantity", "unit")


class PriceResource(resources.ModelResource):
    product = fields.Field(
        attribute="product",
        column_name="product",
        widget=ForeignKeyWidget(Product, "sku"),
    )
    price_type = fields.Field(
        attribute="price_type",
        column_name="price_type",
        widget=ForeignKeyWidget(PriceType, "code"),
    )

    class Meta:
        model = Price
        fields = (
            "product",
            "price_type",
            "value",
            "start_date",
            "end_date",
            "is_active",
            "priority",
            "updated_at",
        )
