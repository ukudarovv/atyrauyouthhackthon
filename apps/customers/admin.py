from django.contrib import admin
from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        'phone_e164', 'business', 'redeems_count', 'issues_count', 
        'recency_days', 'r_score', 'f_score', 'm_score', 'last_redeem_at'
    )
    list_filter = (
        'business', 'r_score', 'f_score', 'm_score', 'created_at'
    )
    search_fields = ('phone_e164', 'business__name')
    readonly_fields = (
        'created_at', 'updated_at', 'rfm_segment', 'is_vip', 
        'is_churn_risk', 'is_new', 'lifetime_value'
    )
    
    fieldsets = (
        (None, {
            'fields': ('business', 'phone_e164', 'tags')
        }),
        ('Активность', {
            'fields': (
                'first_seen', 'last_issue_at', 'last_redeem_at',
                'issues_count', 'redeems_count', 'redeem_amount_total'
            )
        }),
        ('RFM Анализ', {
            'fields': (
                'recency_days', 'r_score', 'f_score', 'm_score',
                'rfm_segment', 'is_vip', 'is_churn_risk', 'is_new', 'lifetime_value'
            ),
            'classes': ('collapse',)
        }),
        ('Метаданные', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('business')
