from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import (
    ContactPoint, MessageTemplate, Blast, BlastRecipient, 
    DeliveryAttempt, ShortLink, ShortLinkClick, MessagePreference
)


@admin.register(ContactPoint)
class ContactPointAdmin(admin.ModelAdmin):
    list_display = ('value', 'type', 'business', 'customer', 'verified', 'opt_in', 'last_seen_at')
    list_filter = ('type', 'verified', 'opt_in', 'business', 'created_at')
    search_fields = ('value', 'customer__phone_e164', 'business__name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (None, {
            'fields': ('business', 'customer', 'type', 'value')
        }),
        ('Статус', {
            'fields': ('verified', 'opt_in', 'last_seen_at')
        }),
        ('Настройки', {
            'fields': ('cost_weight', 'metadata')
        }),
        ('Техническая информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'channel', 'locale', 'business', 'is_active', 'a_b_bucket')
    list_filter = ('channel', 'locale', 'is_active', 'a_b_bucket', 'business')
    search_fields = ('name', 'subject', 'body_text')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (None, {
            'fields': ('business', 'name', 'channel', 'locale')
        }),
        ('Содержимое', {
            'fields': ('subject', 'body_text', 'body_html')
        }),
        ('Персонализация', {
            'fields': ('variables',),
            'description': 'JSON список доступных переменных'
        }),
        ('A/B тестирование', {
            'fields': ('a_b_bucket',)
        }),
        ('Настройки', {
            'fields': ('is_active', 'metadata')
        }),
        ('Техническая информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(Blast)
class BlastAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'status', 'trigger', 'total_recipients', 'delivery_rate_display', 'conversion_rate_display', 'created_at')
    list_filter = ('status', 'trigger', 'business', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('total_recipients', 'sent_count', 'delivered_count', 'opened_count', 'clicked_count', 'converted_count', 'current_cost', 'created_at', 'updated_at')
    
    fieldsets = (
        (None, {
            'fields': ('business', 'name', 'description')
        }),
        ('Настройки рассылки', {
            'fields': ('trigger', 'status', 'segment', 'custom_filter')
        }),
        ('Стратегия', {
            'fields': ('strategy',),
            'description': 'JSON с настройками каскада каналов'
        }),
        ('Планирование', {
            'fields': ('schedule_at',)
        }),
        ('Бюджет', {
            'fields': ('budget_cap', 'current_cost')
        }),
        ('Метрики', {
            'fields': ('total_recipients', 'sent_count', 'delivered_count', 'opened_count', 'clicked_count', 'converted_count'),
            'classes': ('collapse',)
        }),
        ('Техническая информация', {
            'fields': ('started_at', 'completed_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def delivery_rate_display(self, obj):
        rate = obj.delivery_rate()
        if rate > 90:
            color = 'green'
        elif rate > 70:
            color = 'orange'
        else:
            color = 'red'
        return format_html('<span style="color: {};">{:.1f}%</span>', color, rate)
    delivery_rate_display.short_description = 'Доставляемость'
    
    def conversion_rate_display(self, obj):
        rate = obj.conversion_rate()
        if rate > 5:
            color = 'green'
        elif rate > 1:
            color = 'orange'
        else:
            color = 'red'
        return format_html('<span style="color: {};">{:.2f}%</span>', color, rate)
    conversion_rate_display.short_description = 'Конверсия'


@admin.register(BlastRecipient)
class BlastRecipientAdmin(admin.ModelAdmin):
    list_display = ('blast', 'customer', 'status', 'current_step', 'attempts_count', 'total_cost', 'converted_at')
    list_filter = ('status', 'blast__business', 'blast', 'created_at')
    search_fields = ('customer__phone_e164', 'blast__name')
    readonly_fields = ('attempts_count', 'total_cost', 'created_at', 'updated_at')
    
    fieldsets = (
        (None, {
            'fields': ('blast', 'customer', 'contact_points')
        }),
        ('Состояние', {
            'fields': ('status', 'current_step', 'next_attempt_at')
        }),
        ('Метрики', {
            'fields': ('attempts_count', 'last_opened_at', 'last_clicked_at', 'converted_at', 'total_cost')
        }),
        ('Техническая информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(DeliveryAttempt)
class DeliveryAttemptAdmin(admin.ModelAdmin):
    list_display = ('contact_point', 'channel', 'provider', 'status', 'cost', 'sent_at', 'delivered_at')
    list_filter = ('channel', 'provider', 'status', 'blast_recipient__blast__business', 'sent_at')
    search_fields = ('contact_point__value', 'external_id', 'blast_recipient__blast__name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (None, {
            'fields': ('blast_recipient', 'contact_point', 'template')
        }),
        ('Отправка', {
            'fields': ('channel', 'provider', 'subject', 'body')
        }),
        ('Результат', {
            'fields': ('status', 'external_id', 'error_message')
        }),
        ('Временные метки', {
            'fields': ('sent_at', 'delivered_at', 'opened_at', 'clicked_at')
        }),
        ('Финансы', {
            'fields': ('cost',)
        }),
        ('Техническая информация', {
            'fields': ('metadata', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(ShortLink)
class ShortLinkAdmin(admin.ModelAdmin):
    list_display = ('short_code', 'original_url_short', 'blast', 'clicks_count', 'unique_clicks_count', 'is_active')
    list_filter = ('business', 'blast', 'is_active', 'created_at')
    search_fields = ('short_code', 'original_url', 'utm_campaign')
    readonly_fields = ('short_code', 'clicks_count', 'unique_clicks_count', 'created_at')
    
    fieldsets = (
        (None, {
            'fields': ('business', 'short_code', 'original_url')
        }),
        ('Связь с рассылкой', {
            'fields': ('blast', 'delivery_attempt')
        }),
        ('UTM параметры', {
            'fields': ('utm_source', 'utm_medium', 'utm_campaign', 'utm_content')
        }),
        ('Метрики', {
            'fields': ('clicks_count', 'unique_clicks_count')
        }),
        ('Настройки', {
            'fields': ('expires_at', 'is_active')
        }),
        ('Техническая информация', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )
    
    def original_url_short(self, obj):
        return obj.original_url[:50] + '...' if len(obj.original_url) > 50 else obj.original_url
    original_url_short.short_description = 'URL'


@admin.register(ShortLinkClick)
class ShortLinkClickAdmin(admin.ModelAdmin):
    list_display = ('short_link', 'ip_address', 'country', 'device_type', 'clicked_at')
    list_filter = ('country', 'device_type', 'clicked_at')
    search_fields = ('short_link__short_code', 'ip_address', 'user_agent')
    readonly_fields = ('clicked_at',)
    
    fieldsets = (
        (None, {
            'fields': ('short_link', 'clicked_at')
        }),
        ('Техническая информация', {
            'fields': ('ip_address', 'user_agent', 'referer', 'fingerprint')
        }),
        ('Геолокация и устройство', {
            'fields': ('country', 'device_type')
        })
    )


@admin.register(MessagePreference)
class MessagePreferenceAdmin(admin.ModelAdmin):
    list_display = ('customer', 'business', 'locale', 'max_messages_per_day', 'allow_promotional')
    list_filter = ('business', 'locale', 'allow_promotional', 'allow_transactional')
    search_fields = ('customer__phone_e164', 'business__name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (None, {
            'fields': ('business', 'customer')
        }),
        ('Предпочтения каналов', {
            'fields': ('preferred_channels',),
            'description': 'JSON список каналов в порядке приоритета'
        }),
        ('Время отправки', {
            'fields': ('quiet_hours_start', 'quiet_hours_end', 'timezone')
        }),
        ('Язык', {
            'fields': ('locale',)
        }),
        ('Лимиты частоты', {
            'fields': ('max_messages_per_day', 'max_messages_per_week')
        }),
        ('Типы сообщений', {
            'fields': ('allow_promotional', 'allow_transactional', 'allow_expiry_reminders')
        }),
        ('Техническая информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
