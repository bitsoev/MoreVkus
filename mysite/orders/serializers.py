from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .models import Orders, OrderItems, DeliveryAddress


class OrderDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItems
        fields = ['product', 'price_per_unit', 'quantity', 'total_price']



class DeliveryAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryAddress
        fields = ['city', 'street', 'house', 'apartment', 'comment']


class OrderItemsSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItems
        fields = ['product', 'price_per_unit', 'quantity', 'total_price']


class OrdersSerializer(serializers.ModelSerializer):
    items = OrderItemsSerializer(many=True)

    class Meta:
        model = Orders
        fields = ['id', 'user', 'address', 'status', 'order_sum', 'created_dttm', 'items']

    def update(self, instance, validated_data):
        nested_data = validated_data.pop('items', None)

        # Обновляем основную модель
        instance.user = validated_data.get('user', instance.customer)
        instance.address = validated_data.get('address', instance.address)
        instance.status = validated_data.get('status', instance.status)
        instance.save()

        if nested_data:
            existing_item_ids = []
            total_sum = 0  # Переменная для хранения общей суммы заказа

            for nested_item in nested_data:
                nested_id = nested_item.get('id')
                total_sum += float(nested_item['total_price'])  # Добавляем цену текущего элемента к общей сумме

                if nested_id:
                    # Обновляем существующий объект
                    try:
                        nested_instance = instance.items.get(id=nested_id)
                        for attr, value in nested_item.items():
                            setattr(nested_instance, attr, value)
                        nested_instance.save()
                        existing_item_ids.append(nested_id)
                    except OrderItems.DoesNotExist:
                        raise ValidationError(f"Элемент с ID {nested_id} не найден.")
                else:
                    # Создаем новый объект
                    new_item = OrderItems.objects.create(order=instance, **nested_item)
                    existing_item_ids.append(new_item.id)

            # Удаляем элементы, которые не переданы в запросе
            instance.items.exclude(id__in=existing_item_ids).delete()

            # Обновляем общую сумму заказа
            instance.order_sum = total_sum
            instance.save()

        return instance
