from rest_framework import generics
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.settings import api_settings
from rest_framework.authtoken.models import Token
from rest_framework.response import Response

from .serializers import UserSerializer, AuthTokenSerializer

# Представление для регистрации пользователя
class CreateUserView(generics.CreateAPIView):
    serializer_class = UserSerializer

# Представление для авторизации пользователя и получения токена
class CreateTokenView(ObtainAuthToken):
    serializer_class = AuthTokenSerializer
    renderer_classes = api_settings.DEFAULT_RENDERER_CLASSES

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, created = Token.objects.get_or_create(user=user)
        return Response({'token': token.key})