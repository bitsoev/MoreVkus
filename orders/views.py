from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.template.context_processors import request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status, viewsets, generics, permissions

from django.db.models import F

from products.models import Product
from orders.models import Orders
from orders.models import OrderItems

from .models import DeliveryAddress
from .permissions import IsOwnerOrAdmin
from .serializers import OrdersSerializer, OrderDetailSerializer


class OrderListView(generics.ListAPIView):
    serializer_class = OrdersSerializer
    authentication_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Orders.objects.filter(user=self.request.user).order_by('-created_at')


class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderDetailSerializer
    authentication_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Orders.objects.filter(user=self.request.user)


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrdersSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:  # админ видит все заказы
            return Orders.objects.all()
        return Orders.objects.filter(user=user)


class CreateOrderView(APIView):
    def post(self, request):
        data = request.data
        user = request.user

        with transaction.atomic():
            # Валидация метода оплаты
            payment_method = data.get('payment_method', 'cash')
            if payment_method not in dict(Orders.PAYMENT_CHOICES).keys():
                return Response(
                    {'error': 'Неверный метод оплаты'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Обработка адреса доставки
            address_id = data.get('address_id')
            address_data = data.get('address', {})

            if address_id:
                address = get_object_or_404(
                    DeliveryAddress,
                    id=address_id,
                    user=user
                )
            elif address_data:
                address = DeliveryAddress.objects.create(
                    user=user,
                    city=address_data.get('city', ''),
                    street=address_data.get('street', ''),
                    house=address_data.get('house', ''),
                    apartment=address_data.get('apartment', ''),
                    comment=address_data.get('comment', '')
                )
            else:
                return Response(
                    {'error': 'Требуется указать address_id или данные адреса'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Создание заказа
            order = Orders.objects.create(
                user=user,
                address=address,
                payment_method=payment_method,
                status='new'  # Статус по умолчанию
            )

            # Обработка товаров
            order_sum = 0
            items = data.get("items", [])

            if not items:
                return Response(
                    {'error': 'Невозможно создать заказ без товаров'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            for item in items:
                product = get_object_or_404(Product, id=item['product_id'])
                quantity = item.get('quantity', 1)
                price = product.price

                # Проверка достаточности товара на складе
                if product.stock < quantity:
                    return Response(
                        {'error': f'Недостаточно товара "{product.name}" на складе. Доступно: {product.stock}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Уменьшение количества товара на складе
                Product.objects.filter(id=product.id, stock__gte=quantity).update(stock=F('stock') - quantity)

                OrderItems.objects.create(
                    order=order,
                    product=product,
                    price_per_unit=price,
                    quantity=quantity,
                    total_price=price * quantity
                )
                order_sum += price * quantity

            # Обновление суммы заказа
            order.order_sum = order_sum
            order.save()

            # Здесь можно добавить логику оплаты, если метод 'card' или 'sbp'
            if payment_method in ['card', 'sbp']:
                self._initiate_payment(order)  # Ваш метод для инициирования платежа

            return Response({
                'success': True,
                'order_id': order.id,
                'order_sum': float(order_sum),
                'payment_method': payment_method,
                'status': 'new'
            }, status=status.HTTP_201_CREATED)

    def _initiate_payment(self, order):
        """Вспомогательный метод для обработки платежа"""
        # Реализуйте интеграцию с платежной системой здесь
        pass


class UpdateOrdersView(APIView):
    def post(self, request, pk):
        status = request.data.get('status')
        order = get_object_or_404(Orders, id=pk)

        if status not in dict(Orders.STATUS_CHOICES):
            return Response({"error": "Некорректный статус"},status=status.HTTP_400_BAD_REQUEST)

        order.status = status
        order.save()
        return Response({'succses': True, 'status': order.status})


class OrderCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            order = Orders.objects.get(user = request.user, pk=pk)
            if order.status in ['new', 'confirmed']:
                order.status = 'cancelled'
                order.save()
                return Response({"status": "cancelled"})
            return Response({"error": "Нельзя отменить заказ на этом этапе"}, status=400)
        except order.DoesNotExist:
            Response({'error': 'Заказ не найден'}, status=404)


class OrderTrackView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            order = Orders.objects.get(user=request.user, pk=pk)
            return Response({'order_id': pk,
                             'status': order.status,
                             'last_update': order.updated_at})
        except order.DoesNotExist:
            Response({'error': 'Заказ не найден'}, status=404)


class OrderRepeatView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            # 1. Получаем оригинальный заказ с проверкой существования
            original = Orders.objects.get(user=request.user, pk=pk)

            # 2. Создаем новый заказ
            new_order = Orders.objects.create(
                user=request.user,
                address=original.address,
                order_sum=0,  # Временно 0, пересчитаем ниже
                payment_method=original.payment_method,
                # Другие необходимые поля из original
            )

            order_sum = 0
            skipped_products = []

            # 3. Копируем товары из оригинального заказа
            for item in original.items.all():  # Используем правильное related_name
                if not item.product.is_active:  # Исправлено is_activ -> is_active
                    skipped_products.append(item.product.name)
                    continue

                # 4. Создаем позицию в новом заказе с ТЕКУЩЕЙ ценой
                OrderItems.objects.create(
                    order=new_order,  # Исправлено: item.order -> new_order
                    product=item.product,
                    quantity=item.quantity,
                    price_per_unit=item.product.price  # Текущая цена
                )
                order_sum += item.quantity * item.product.price

            # 5. Обновляем сумму заказа
            new_order.order_sum = order_sum
            new_order.save()

            # 6. Формируем ответ
            response_data = {
                'id': new_order.id,
                'order_sum': order_sum,
                'message': 'Заказ успешно повторен'
            }

            if skipped_products:
                response_data['skipped_products'] = skipped_products
                response_data['warning'] = 'Некоторые товары недоступны'

            return Response(response_data)

        except Orders.DoesNotExist:
            return Response({'error': 'Заказ не найден'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


def RettUser(request):
    user = request.user

    return HttpResponse(user)