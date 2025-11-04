from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import OrderItems


@receiver([post_save, post_delete], sender=OrderItems)
def update_order_total(sender, instance, **kwargs):
    """Автоматически пересчитывает сумму заказа при изменении позиций"""
    if instance.order_id:
        instance.order.recalc_total()