from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status, viewsets, generics, permissions

from products.models import Product, Stock
from .models import Orders, OrderItems, DeliveryAddress
from .permissions import IsOwnerOrAdmin
from .serializers import OrdersSerializer, OrderDetailSerializer, DeliveryAddressSerializer


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
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        data = request.data
        user = request.user

        with transaction.atomic():
            payment_method = data.get('payment_method', 'cash')
            if payment_method not in dict(Orders.PAYMENT_CHOICES):
                return Response({'error': 'Неверный метод оплаты'}, status=400)

            address_id = data.get('address_id')
            address_data = data.get('address', {})

            if address_id:
                address = get_object_or_404(DeliveryAddress, id=address_id, user=user)
            elif address_data:
                address = DeliveryAddress.objects.create(user=user, **address_data)
            else:
                return Response({'error': 'Не указан адрес'}, status=400)

            order = Orders.objects.create(user=user, address=address, payment_method=payment_method, status='new')

            order_sum = 0
            items = data.get("items", [])
            if not items:
                return Response({'error': 'Пустой заказ'}, status=400)

            for item in items:
                product = get_object_or_404(Product, id=item['product_id'])
                quantity = int(item.get('quantity', 1))

                total_available = product.stock_cache
                if total_available < quantity:
                    return Response(
                        {'error': f'Недостаточно товара "{product.name}" на складе ({total_available} шт.)'},
                        status=400
                    )

                price = product.price
                total_price = price * quantity

                OrderItems.objects.create(
                    order=order,
                    product=product,
                    price_per_unit=price,
                    quantity=quantity,
                    total_price=total_price
                )

                order_sum += total_price

                product.stock_cache -= quantity
                product.save(update_fields=['stock_cache'])

            order.order_sum = order_sum
            order.save()

            return Response({
                'success': True,
                'order_id': order.id,
                'order_sum': float(order_sum),
                'status': order.status
            }, status=201)


class OrderRepeatView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            original = Orders.objects.get(user=request.user, pk=pk)
        except Orders.DoesNotExist:
            return Response({'error': 'Заказ не найден'}, status=404)

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
                if not product.is_active:
                    skipped.append(product.name)
                    continue

                qty = item.quantity
                if product.stock_cache < qty:
                    skipped.append(f"{product.name} (недостаточно)")
                    continue

                price = product.price
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

            new_order.order_sum = total
            new_order.save()

            return Response({
                'id': new_order.id,
                'order_sum': total,
                'skipped': skipped,
                'message': 'Заказ повторен'
            })
