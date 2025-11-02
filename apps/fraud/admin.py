from django.contrib import admin
from .models import RiskEvent

@admin.register(RiskEvent)
class RiskEventAdmin(admin.ModelAdmin):
    list_display = ('business', 'kind', 'score', 'decision', 'phone', 'ip', 'created_at', 'resolved')
    list_filter = ('business', 'kind', 'decision', 'resolved', 'created_at')
    search_fields = ('phone', 'ip')
    readonly_fields = ('created_at',)
    
    fieldsets = (
        (None, {
            'fields': ('business', 'kind', 'campaign_id', 'coupon')
        }),
        ('Контакты', {
            'fields': ('phone', 'ip', 'ua', 'utm')
        }),
        ('Анализ риска', {
            'fields': ('score', 'reasons', 'decision', 'resolved')
        }),
        ('Метаданные', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
