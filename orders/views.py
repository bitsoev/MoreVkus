from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status, viewsets, generics, permissions

from products.models import Product, Price
from .models import Orders, OrderItems, DeliveryAddress
from .permissions import IsOwnerOrAdmin
from .serializers import OrdersSerializer


class OrderListView(generics.ListAPIView):
    serializer_class = OrdersSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Orders.objects.filter(user=self.request.user).order_by('-created_dttm')


class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrdersSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Orders.objects.filter(user=self.request.user)


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrdersSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Orders.objects.all()
        return Orders.objects.filter(user=user)


class CreateOrderView(APIView):
    """
    Создание нового заказа (используется мобильным приложением)
    При создании — сразу списывает остатки со склада и пересчитывает кэш.
    """
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        data = request.data
        user = request.user

        # === Проверка метода оплаты ===
        payment_method = data.get('payment_method', 'cash')
        if payment_method not in dict(Orders.PAYMENT_CHOICES):
            return Response({'error': 'Неверный метод оплаты'}, status=status.HTTP_400_BAD_REQUEST)

        # === Определение адреса ===
        address_id = data.get('address_id')
        address_data = data.get('address', {})

        if address_id:
            address = get_object_or_404(DeliveryAddress, id=address_id, user=user)
        elif address_data:
            address = DeliveryAddress.objects.create(user=user, **address_data)
        else:
            return Response({'error': 'Не указан адрес'}, status=status.HTTP_400_BAD_REQUEST)

        # === Создаём заказ ===
        order = Orders.objects.create(
            user=user,
            address=address,
            payment_method=payment_method,
            status='new'
        )

        # === Обработка позиций ===
        items = data.get('items', [])
        if not items:
            return Response({'error': 'Пустой заказ'}, status=status.HTTP_400_BAD_REQUEST)

        order_total = 0
        insufficient = []

        for item in items:
            product_id = item.get('product_id')
            quantity = int(item.get('quantity', 1))
            warehouse_id = item.get('warehouse_id')

            # Проверяем существование продукта
            product = get_object_or_404(Product, id=product_id, is_active=True)

            # Получаем цену — берём базовую (например, "Розничная")
            price_obj = product.prices.first()
            if not price_obj:
                return Response({'error': f'У товара "{product.name}" нет цены'}, status=status.HTTP_400_BAD_REQUEST)

            price = price_obj.value

            # === Определяем склад ===
            stock_qs = Stock.objects.select_for_update().filter(product=product)
            if warehouse_id:
                stock_qs = stock_qs.filter(warehouse_id=warehouse_id)

            stock = stock_qs.first()
            if not stock or stock.quantity < quantity:
                insufficient.append(product.name)
                continue

            # === Списание остатков ===
            stock.quantity = F('quantity') - quantity
            stock.save(update_fields=['quantity'])

            # === Пересчёт кеша stock_cache ===
            total_stock = product.stocks.aggregate(total=Sum('quantity'))['total'] or 0
            product.stock_cache = total_stock
            product.save(update_fields=['stock_cache'])

            # === Создание позиции ===
            total_price = price * quantity
            OrderItems.objects.create(
                order=order,
                product=product,
                warehouse=stock.warehouse,
                price_per_unit=price,
                quantity=quantity,
                total_price=total_price
            )
            order_total += total_price

        # === Проверяем, были ли пропущенные товары ===
        if insufficient:
            order.delete()
            return Response({
                'error': 'Недостаточно остатков',
                'details': insufficient
            }, status=status.HTTP_400_BAD_REQUEST)

        # === Завершаем заказ ===
        order.order_sum = order_total
        order.save(update_fields=['order_sum'])

        return Response({
            'success': True,
            'order_id': order.id,
            'order_sum': float(order_total),
            'status': order.status,
            'message': 'Заказ успешно создан'
        }, status=status.HTTP_201_CREATED)


class OrderRepeatView(APIView):
    """
    Повторение ранее созданного заказа пользователем.
    Проверяет остатки и актуальные цены.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            original = Orders.objects.get(user=request.user, pk=pk)
        except Orders.DoesNotExist:
            return Response({'error': 'Заказ не найден.'}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            new_order = Orders.objects.create(
                user=request.user,
                address=original.address,
                payment_method=original.payment_method,
                status='new'
            )

            total = 0
            skipped = []

            for item in original.items.all():
                product = item.product
                qty = item.quantity

                if not product.is_active:
                    skipped.append(f"{product.name} (товар скрыт)")
                    continue

                if product.stock_cache < qty:
                    skipped.append(f"{product.name} (недостаточно на складе)")
                    continue

                price = (
                    Price.objects.filter(product=product, price_type__name="Розничная")
                    .order_by('-updated_at')
                    .values_list('value', flat=True)
                    .first()
                )

                if price is None:
                    skipped.append(f"{product.name} (нет цены)")
                    continue

                OrderItems.objects.create(
                    order=new_order,
                    product=product,
                    quantity=qty,
                    price_per_unit=price,
                    total_price=price * qty
                )

                total += price * qty
                product.stock_cache -= qty
                product.save(update_fields=['stock_cache'])

            if not new_order.items.exists():
                new_order.delete()
                return Response(
                    {"error": "Ни один товар не удалось повторить.", "skipped": skipped},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            new_order.order_sum = total
            new_order.save()

            return Response(
                {
                    "id": new_order.id,
                    "order_sum": float(total),
                    "skipped": skipped,
                    "message": "Заказ успешно повторён.",
                },
                status=status.HTTP_201_CREATED,
            )


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def cancel_order(request, pk):
    """
    Отменяет заказ и возвращает товары на склад.
    Можно вызывать только для своих заказов, если они ещё не отменены/доставлены.
    """
    user = request.user
    order = get_object_or_404(Orders, id=pk)

    # Проверяем права
    if not user.is_staff and order.user != user:
        return Response({'error': 'Недостаточно прав'}, status=status.HTTP_403_FORBIDDEN)

    # Проверяем статус
    if order.status == 'cancelled':
        return Response({'error': 'Заказ уже отменён'}, status=status.HTTP_400_BAD_REQUEST)
    if order.status in ['delivered', 'completed']:
        return Response({'error': 'Доставленные заказы нельзя отменить'}, status=status.HTTP_400_BAD_REQUEST)

    # Возвращаем остатки
    for item in order.items.select_related('product', 'warehouse'):
        product = item.product
        qty = item.quantity

        stock = Stock.objects.select_for_update().filter(
            product=product,
            warehouse=item.warehouse
        ).first()

        if stock:
            stock.quantity = F('quantity') + qty
            stock.save(update_fields=['quantity'])

        # Пересчёт stock_cache
        total = product.stocks.aggregate(total=Sum('quantity'))['total'] or 0
        product.stock_cache = total
        product.save(update_fields=['stock_cache'])

    # Обновляем заказ
    order.status = 'cancelled'
    order.save(update_fields=['status'])

    return Response({
        'success': True,
        'message': f'Заказ #{order.id} отменён, остатки возвращены на склад.'
    }, status=status.HTTP_200_OK)