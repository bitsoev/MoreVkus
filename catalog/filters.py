import django_filters
from .models import Product


class DynamicProductFilter(django_filters.FilterSet):
    class Meta:
        model = Product
        fields = {field.name: ['exact'] for field in Product._meta.fields}
