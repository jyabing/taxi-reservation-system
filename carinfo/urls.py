from django.urls import path
from . import views

app_name = 'carinfo'  # ← 可选，如果你想使用 carinfo:car_list 的写法

urlpatterns = [
    path('', views.car_list, name='car_list'),  # ← 确保这行存在
    path('create/', views.car_create, name='car_create'),
    path('<int:pk>/edit/', views.car_edit, name='car_edit'),
    path('<int:pk>/delete/', views.car_delete, name='car_delete'),
]