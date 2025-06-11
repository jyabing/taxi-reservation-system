from django.contrib import admin
from .models import Car

@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = ('license_plate', 'brand', 'model', 'year', 'is_active')
    search_fields = ('license_plate', 'brand', 'model')
    list_filter = ('is_active',)