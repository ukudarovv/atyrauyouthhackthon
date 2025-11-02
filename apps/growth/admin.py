from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import MysteryDropTier, MysteryDrop, MysteryDropAttempt, PowerHour


@admin.register(MysteryDropTier)
class MysteryDropTierAdmin(admin.ModelAdmin):
    list_display = ('name', 'discount_percent', 'probability', 'emoji', 'color_preview', 'is_active', 'order')
    list_filter = ('is_active', 'discount_percent')
    search_fields = ('name',)
    list_editable = ('probability', 'is_active', 'order')
    ordering = ['order', 'discount_percent']
    
    def color_preview(self, obj):
        return format_html(
            '<div style="width: 20px; height: 20px; background-color: {}; border: 1px solid #ccc;"></div>',
            obj.color
        )
    color_preview.short_description = 'Цвет'


@admin.register(MysteryDrop)
class MysteryDropAdmin(admin.ModelAdmin):
    list_display = ('title', 'campaign', 'business', 'enabled', 'total_attempts', 'total_wins', 'win_rate', 'created_at')
    list_filter = ('business', 'enabled', 'auto_wallet_creation', 'send_notification', 'created_at')
    search_fields = ('title', 'campaign__name', 'business__name')
    readonly_fields = ('total_attempts', 'total_wins', 'total_redeems', 'created_at', 'updated_at')
    filter_horizontal = ('tiers',)
    
    fieldsets = (
        (None, {
            'fields': ('business', 'campaign', 'title', 'subtitle')
        }),
        ('Настройки призов', {
            'fields': ('tiers',),
            'description': 'Выберите уровни призов для этого Mystery Drop'
        }),
        ('Ограничения', {
            'fields': ('daily_cap_per_phone', 'daily_cap_total')
        }),
        ('Временные рамки', {
            'fields': ('starts_at', 'ends_at')
        }),
        ('Интерфейс', {
            'fields': ('scratch_enabled', 'shake_enabled', 'background_color'),
            'classes': ('collapse',)
        }),
        ('Интеграции', {
            'fields': ('auto_wallet_creation', 'send_notification')
        }),
        ('Статус', {
            'fields': ('enabled',)
        }),
        ('Статистика', {
            'fields': ('total_attempts', 'total_wins', 'total_redeems'),
            'classes': ('collapse',)
        }),
        ('Техническая информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def win_rate(self, obj):
        if obj.total_attempts > 0:
            rate = (obj.total_wins / obj.total_attempts) * 100
            color = 'green' if rate > 80 else 'orange' if rate > 50 else 'red'
            return format_html('<span style="color: {};">{:.1f}%</span>', color, rate)
        return '—'
    win_rate.short_description = 'Процент побед'


@admin.register(MysteryDropAttempt)
class MysteryDropAttemptAdmin(admin.ModelAdmin):
    list_display = ('phone', 'mystery_drop', 'won', 'tier', 'coupon_code', 'wallet_status', 'created_at')
    list_filter = ('won', 'mystery_drop__business', 'mystery_drop', 'tier', 'created_at')
    search_fields = ('phone', 'customer__phone_e164', 'coupon__code')
    readonly_fields = ('created_at', 'risk_score', 'risk_flags')
    
    fieldsets = (
        (None, {
            'fields': ('mystery_drop', 'phone', 'customer')
        }),
        ('Результат', {
            'fields': ('won', 'tier', 'coupon', 'wallet_pass')
        }),
        ('Техническая информация', {
            'fields': ('ip_address', 'user_agent', 'session_data'),
            'classes': ('collapse',)
        }),
        ('Антифрод', {
            'fields': ('risk_score', 'risk_flags'),
            'classes': ('collapse',)
        }),
        ('Время', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )
    
    def coupon_code(self, obj):
        if obj.coupon:
            return obj.coupon.code
        return '—'
    coupon_code.short_description = 'Код купона'
    
    def wallet_status(self, obj):
        if obj.wallet_pass:
            if obj.wallet_pass.is_active:
                return format_html('<span style="color: green;">✅ Активна</span>')
            else:
                return format_html('<span style="color: red;">❌ Неактивна</span>')
        return '—'
    wallet_status.short_description = 'Wallet карта'


@admin.register(PowerHour)
class PowerHourAdmin(admin.ModelAdmin):
    list_display = ('title', 'campaign', 'business', 'status', 'starts_at', 'duration_display', 'metrics_display')
    list_filter = ('business', 'status', 'auto_wallet_update', 'send_blast', 'starts_at')
    search_fields = ('title', 'campaign__name', 'business__name')
    readonly_fields = ('ends_at', 'blast_sent', 'wallet_updated', 'coupons_issued', 'coupons_redeemed', 'created_at', 'updated_at')
    
    fieldsets = (
        (None, {
            'fields': ('business', 'campaign', 'title', 'discount_text')
        }),
        ('Время', {
            'fields': ('duration_minutes', 'starts_at', 'ends_at')
        }),
        ('Wallet настройки', {
            'fields': ('auto_wallet_update', 'wallet_background_color', 'wallet_text_color')
        }),
        ('Рассылка', {
            'fields': ('send_blast', 'blast_segment')
        }),
        ('Статус', {
            'fields': ('status',)
        }),
        ('Метрики', {
            'fields': ('blast_sent', 'wallet_updated', 'coupons_issued', 'coupons_redeemed'),
            'classes': ('collapse',)
        }),
        ('Техническая информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def duration_display(self, obj):
        return f"{obj.duration_minutes} мин"
    duration_display.short_description = 'Длительность'
    
    def metrics_display(self, obj):
        return format_html(
            'Рассылки: {} | Wallet: {} | Выдано: {} | Погашено: {}',
            obj.blast_sent,
            obj.wallet_updated,
            obj.coupons_issued,
            obj.coupons_redeemed
        )
    metrics_display.short_description = 'Метрики'
