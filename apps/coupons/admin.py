from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import Coupon

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'campaign', 'phone', 'status', 'wallet_actions', 'issued_at', 'expires_at')
    list_filter = ('status', 'campaign', 'issued_at')
    search_fields = ('code', 'phone', 'campaign__name')
    readonly_fields = ('code', 'issued_at', 'wallet_pass_info')
    date_hierarchy = 'issued_at'
    
    fieldsets = (
        (None, {
            'fields': ('code', 'campaign', 'phone', 'status')
        }),
        ('Временные рамки', {
            'fields': ('issued_at', 'expires_at')
        }),
        ('Антифрод', {
            'fields': ('risk_score', 'risk_flag', 'metadata'),
            'classes': ('collapse',)
        }),
        ('Google Wallet', {
            'fields': ('wallet_pass_info',),
            'classes': ('collapse',)
        })
    )
    
    def wallet_actions(self, obj):
        """Действия для Google Wallet"""
        from apps.wallet.models import WalletPass
        
        wallet_pass = WalletPass.objects.filter(coupon=obj).first()
        
        if wallet_pass:
            detail_url = reverse('admin:wallet_walletpass_change', args=[wallet_pass.pk])
            return format_html(
                '<a href="{}" class="button">📱 Просмотр карты</a>',
                detail_url
            )
        else:
            create_url = reverse('wallet:create_pass', args=[obj.pk])
            return format_html(
                '<a href="{}" class="button" target="_blank">📱 Создать карту</a>',
                create_url
            )
    
    wallet_actions.short_description = 'Google Wallet'
    
    def wallet_pass_info(self, obj):
        """Информация о связанной Wallet карте"""
        from apps.wallet.models import WalletPass
        
        wallet_pass = WalletPass.objects.filter(coupon=obj).first()
        
        if wallet_pass:
            detail_url = reverse('wallet:pass_detail', args=[wallet_pass.pk])
            return format_html(
                'Wallet карта: <a href="{}" target="_blank">{}</a><br>'
                'Статус: {}<br>'
                'Создана: {}',
                detail_url,
                wallet_pass.title,
                wallet_pass.get_status_display(),
                wallet_pass.created_at.strftime('%d.%m.%Y %H:%M')
            )
        else:
            create_url = reverse('wallet:create_pass', args=[obj.pk])
            return format_html(
                'Wallet карта не создана. <a href="{}" target="_blank">Создать карту</a>',
                create_url
            )
    
    wallet_pass_info.short_description = 'Google Wallet карта'