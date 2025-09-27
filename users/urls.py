from django.urls import path
from .views import CreateUserView, CreateTokenView, ManageUserView, LogoutView

urlpatterns = [
    path('register/', CreateUserView.as_view(), name='register'),
    path('login/', CreateTokenView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('me/', ManageUserView.as_view(), name='me'),
]