from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Sum

from .models import Stock, Product


@receiver(post_save, sender=Stock)
@receiver(post_delete, sender=Stock)
def update_product_stock_cache(sender, instance, **kwargs):
    product = instance.product
    total = product.stocks.aggregate(total=Sum('quantity'))['total'] or 0
    product.stock_cache = total
    product.save(update_fields=['stock_cache'])
