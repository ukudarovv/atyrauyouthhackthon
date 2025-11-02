from django.contrib import admin
from .models import WalletPass, WalletClass


@admin.register(WalletClass)
class WalletClassAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'platform', 'review_status', 'is_active', 'created_at')
    list_filter = ('platform', 'review_status', 'is_active', 'created_at')
    search_fields = ('name', 'business__name', 'class_id')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (None, {
            'fields': ('business', 'platform', 'class_id', 'name', 'description')
        }),
        ('Визуальное оформление', {
            'fields': ('background_color', 'logo_url', 'hero_image_url')
        }),
        ('Локации', {
            'fields': ('locations',),
            'description': 'JSON массив с локациями для Nearby уведомлений'
        }),
        ('Статус', {
            'fields': ('review_status', 'is_active')
        }),
        ('Техническая информация', {
            'fields': ('metadata', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(WalletPass)
class WalletPassAdmin(admin.ModelAdmin):
    list_display = ('title', 'customer_phone', 'business', 'platform', 'status', 'created_at')
    list_filter = ('platform', 'status', 'business', 'created_at')
    search_fields = ('title', 'customer_phone', 'customer_email', 'barcode_value', 'object_id')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (None, {
            'fields': ('business', 'coupon', 'campaign')
        }),
        ('Клиент', {
            'fields': ('customer_phone', 'customer_email')
        }),
        ('Платформа', {
            'fields': ('platform', 'class_id', 'object_id')
        }),
        ('Содержимое', {
            'fields': ('title', 'subtitle', 'barcode_value')
        }),
        ('Статус и сроки', {
            'fields': ('status', 'valid_from', 'valid_until')
        }),
        ('Уведомления', {
            'fields': ('notification_sent_24h', 'notification_sent_1h'),
            'classes': ('collapse',)
        }),
        ('Техническая информация', {
            'fields': ('metadata', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('business', 'coupon', 'campaign')
