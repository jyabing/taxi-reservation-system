from django.contrib import admin
from .models import Vehicle, Reservation, CarouselImage
from django.utils.html import format_html

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('license_plate', 'model', 'status', 'inspection_date')
    list_display_links = ('license_plate',)
    search_fields = ('license_plate', 'model')
    list_filter = ('status',)
    ordering = ('license_plate',)


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'driver', 'date', 'start_time', 'end_time', 'status')
    list_filter = ('status', 'date')
    actions = ['approve_reservations']

    @admin.action(description="✅ 通过选中预约")
    def approve_reservations(self, request, queryset):
        updated = queryset.filter(status='pending').update(status='reserved')
        self.message_user(request, f"{updated} 条预约已成功通过。")

@admin.register(CarouselImage)
class CarouselImageAdmin(admin.ModelAdmin):
    list_display = ['title', 'order', 'is_active', 'preview']
    list_editable = ['order', 'is_active']

    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="100" />', obj.image.url)
        return "-"
    preview.short_description = "预览"