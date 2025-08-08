from django.forms import model_to_dict
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from .models import Product
from rest_framework import viewsets
from .serializers import ProductSerializers
from django_filters.rest_framework import DjangoFilterBackend
from .filters import DynamicProductFilter


def chek_product_stock(request,product_id):
    product = Product.objects.get(id=product_id)
    return JsonResponse({'stock': Product.product_count})

def add_to_cart(request,product_id):
    product = Product.objects.get(id=product_id)
    if product.product_count > 0:
        return JsonResponse({'status':'added'})
    else:
        return JsonResponse({'status':'out of stock'})


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializers
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id', 'name', 'in_stock']

    def get_queryset(self):
        queryset = super().get_queryset()
        ids = self.request.query_params.get('id', None)

        if ids:
            id_list = ids.split(',')  # Разделяем параметры по запятой
            queryset = queryset.filter(id__in=id_list)

        return queryset



def return_data(model, *args):
    result = {}
    for attribute_name in args:
        result[attribute_name] = getattr(model, attribute_name, None)
    return result


# def testing(request, pk):
#     try:
#         product = Product.objects.get(id=pk)
#         data = return_data(product, "name", "product_count","price")
#         return JsonResponse(data)
#     except Product.DoesNotExist:
#         return JsonResponse({'error': 'Product not found'}, status=404)


def testing(request, pk):
    try:
        beke = Product.objects.get(id=pk)
        serializer = ProductSerializers(beke)
        return JsonResponse(serializer.data)
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Product not found'}, status=404)


def testing_2(request):
    try:
        beke = Product.objects.all()
        serializer = ProductSerializers(beke,many=True)
        return JsonResponse(serializer.data,safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)  # Обработка исключений с возвратом ошибки

#возвращает только товары в наличии
def testing_3(request):
    product = Product.instock.all()
    serializers = ProductSerializers(product, many=True)
    return JsonResponse(serializers.data,safe=False)


#возвращает только товары в наличии, но через ViewSet - Удобнее
class InStockViewSet(viewsets.ModelViewSet):
    queryset = Product.instock.all() #возвращает из бд список тех что в наличии
    serializer_class = ProductSerializers
    filter_backends = [DjangoFilterBackend]
    #filter_class = DynamicProductFilter #Все поля фильтрации с помощью фм DjangoFilterBackend
    filterset_fields = ['name','in_stock','price'] #поля фильтрации с помощью фм DjangoFilterBackend
