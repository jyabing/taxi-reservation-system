from django.urls import path
from . import views

app_name = 'staffbook'

urlpatterns = [
    path('submit_sales/', views.submit_sales, name='submit_sales'),
    path('sales_thanks/', views.sales_thanks, name='sales_thanks'),
]
