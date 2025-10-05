from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from .models import Orders, OrderItems, DeliveryAddress
from products.models import Product


class OrderDetailSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = OrderItems
        fields = ['id', 'product', 'product_name', 'price_per_unit', 'quantity', 'total_price']


class DeliveryAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryAddress
        fields = ['id', 'city', 'street', 'house', 'apartment', 'comment']


class OrderItemsSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = OrderItems
        fields = ['id', 'product', 'product_name', 'price_per_unit', 'quantity', 'total_price']


class OrdersSerializer(serializers.ModelSerializer):
    items = OrderItemsSerializer(many=True, required=False)
    address = DeliveryAddressSerializer()

    class Meta:
        model = Orders
        fields = [
            'id', 'user', 'address', 'status', 'order_sum', 'payment_method',
            'created_dttm', 'updated_at', 'items'
        ]
        read_only_fields = ['order_sum', 'created_dttm', 'updated_at']

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        address_data = validated_data.pop('address')
        user = self.context['request'].user

        address, _ = DeliveryAddress.objects.get_or_create(user=user, **address_data)
        order = Orders.objects.create(user=user, address=address, **validated_data)

        total = 0
        for item_data in items_data:
            product = Product.objects.get(id=item_data['product'].id)
            qty = item_data['quantity']
            if product.stock_cache < qty:
                raise ValidationError(f"Недостаточно товара '{product.name}' на складе.")
            price = product.price
            total_price = price * qty
            OrderItems.objects.create(
                order=order,
                product=product,
                price_per_unit=price,
                quantity=qty,
                total_price=total_price
            )
            total += total_price

            # уменьшаем остаток
            product.stock_cache -= qty
            product.save(update_fields=['stock_cache'])

        order.order_sum = total
        order.save()
        return order

    def update(self, instance, validated_data):
        nested_data = validated_data.pop('items', None)
        instance.status = validated_data.get('status', instance.status)
        instance.save()

        if nested_data:
            existing_item_ids = []
            total_sum = 0

            for nested_item in nested_data:
                nested_id = nested_item.get('id')
                total_sum += float(nested_item['total_price'])

                if nested_id:
                    try:
                        nested_instance = instance.items.get(id=nested_id)
                        for attr, value in nested_item.items():
                            setattr(nested_instance, attr, value)
                        nested_instance.save()
                        existing_item_ids.append(nested_id)
                    except OrderItems.DoesNotExist:
                        raise ValidationError(f"Элемент с ID {nested_id} не найден.")
                else:
                    new_item = OrderItems.objects.create(order=instance, **nested_item)
                    existing_item_ids.append(new_item.id)

            instance.items.exclude(id__in=existing_item_ids).delete()
            instance.order_sum = total_sum
            instance.save()

        return instance
