"""
Django Admin для Instagram интеграции
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    IGAccount, IGMedia, IGComment, IGThreadMessage, 
    IGWebhookEvent, IGDMTemplate
)


@admin.register(IGAccount)
class IGAccountAdmin(admin.ModelAdmin):
    list_display = (
        'username', 'business', 'status', 'followers_count', 
        'days_until_expiry', 'connected_at'
    )
    list_filter = ('status', 'auto_publish_enabled', 'dm_bot_enabled')
    search_fields = ('username', 'business__name', 'ig_user_id')
    readonly_fields = (
        'ig_user_id', 'page_id', 'connected_at', 'last_sync_at',
        'token_expires_at', 'permissions'
    )
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('business', 'username', 'ig_user_id', 'page_id', 'status')
        }),
        ('Профиль', {
            'fields': ('profile_picture_url', 'followers_count')
        }),
        ('Токен доступа', {
            'fields': ('token_expires_at', 'permissions'),
            'classes': ('collapse',)
        }),
        ('Настройки', {
            'fields': (
                'auto_publish_enabled', 'dm_bot_enabled', 
                'comment_moderation_enabled'
            )
        }),
        ('Метаданные', {
            'fields': ('connected_at', 'last_sync_at', 'sync_errors'),
            'classes': ('collapse',)
        })
    )
    
    def days_until_expiry(self, obj):
        days = obj.days_until_expiry
        if days <= 3:
            color = 'red'
        elif days <= 7:
            color = 'orange'
        else:
            color = 'green'
        return format_html(
            '<span style="color: {};">{} дней</span>',
            color, days
        )
    days_until_expiry.short_description = 'До истечения токена'


@admin.register(IGMedia)
class IGMediaAdmin(admin.ModelAdmin):
    list_display = (
        'caption_preview', 'account', 'media_type', 'status',
        'engagement_rate', 'publish_at', 'created_at'
    )
    list_filter = (
        'status', 'media_type', 'account', 'utm_campaign'
    )
    search_fields = ('caption', 'ig_media_id', 'utm_campaign')
    readonly_fields = (
        'ig_media_id', 'creation_id', 'permalink', 'published_at',
        'reach', 'impressions', 'likes', 'comments_count', 'saves', 'shares', 'plays',
        'last_insights_sync', 'engagement_rate'
    )
    
    fieldsets = (
        ('Контент', {
            'fields': ('account', 'media_type', 'caption', 'media_url', 'thumbnail_url')
        }),
        ('Публикация', {
            'fields': ('status', 'publish_at', 'published_at', 'permalink')
        }),
        ('UTM метки', {
            'fields': (
                'utm_source', 'utm_medium', 'utm_campaign', 
                'utm_content', 'utm_term'
            ),
            'classes': ('collapse',)
        }),
        ('Метрики', {
            'fields': (
                'reach', 'impressions', 'likes', 'comments_count', 
                'saves', 'shares', 'plays', 'engagement_rate', 'last_insights_sync'
            ),
            'classes': ('collapse',)
        }),
        ('Instagram API', {
            'fields': ('ig_media_id', 'creation_id', 'error_message'),
            'classes': ('collapse',)
        })
    )
    
    def caption_preview(self, obj):
        preview = (obj.caption[:60] + '...') if len(obj.caption) > 60 else obj.caption
        return preview or '(без подписи)'
    caption_preview.short_description = 'Подпись'
    
    def engagement_rate(self, obj):
        rate = obj.engagement_rate
        if rate > 5:
            color = 'green'
        elif rate > 2:
            color = 'orange'
        else:
            color = 'red'
        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color, rate
        )
    engagement_rate.short_description = 'Engagement'


@admin.register(IGComment)
class IGCommentAdmin(admin.ModelAdmin):
    list_display = (
        'text_preview', 'author_username', 'media', 'ai_sentiment',
        'ai_toxic', 'hidden', 'created_at'
    )
    list_filter = (
        'hidden', 'ai_toxic', 'moderation_action', 'media__account'
    )
    search_fields = ('text', 'author_username', 'ai_summary')
    readonly_fields = (
        'ig_comment_id', 'ig_parent_id', 'author_id', 
        'ai_sentiment', 'ai_toxic', 'ai_labels', 'ai_summary',
        'created_at', 'synced_at'
    )
    
    fieldsets = (
        ('Комментарий', {
            'fields': ('media', 'text', 'author_username', 'author_id')
        }),
        ('Модерация', {
            'fields': (
                'hidden', 'moderated_by', 'moderated_at', 'moderation_action'
            )
        }),
        ('AI анализ', {
            'fields': ('ai_sentiment', 'ai_toxic', 'ai_labels', 'ai_summary'),
            'classes': ('collapse',)
        }),
        ('Instagram API', {
            'fields': ('ig_comment_id', 'ig_parent_id', 'created_at', 'synced_at'),
            'classes': ('collapse',)
        })
    )
    
    def text_preview(self, obj):
        preview = (obj.text[:80] + '...') if len(obj.text) > 80 else obj.text
        return preview
    text_preview.short_description = 'Текст'
    
    actions = ['hide_comments', 'unhide_comments', 'mark_as_toxic']
    
    def hide_comments(self, request, queryset):
        count = queryset.update(hidden=True, moderated_by=request.user)
        self.message_user(request, f'Скрыто комментариев: {count}')
    hide_comments.short_description = 'Скрыть выбранные комментарии'
    
    def unhide_comments(self, request, queryset):
        count = queryset.update(hidden=False, moderated_by=request.user)
        self.message_user(request, f'Показано комментариев: {count}')
    unhide_comments.short_description = 'Показать выбранные комментарии'


@admin.register(IGThreadMessage)
class IGThreadMessageAdmin(admin.ModelAdmin):
    list_display = (
        'text_preview', 'sender_username', 'direction', 
        'is_bot_response', 'is_within_24h_window', 'timestamp'
    )
    list_filter = (
        'direction', 'is_bot_response', 'is_within_24h_window', 
        'account', 'message_type'
    )
    search_fields = ('text', 'sender_username', 'thread_id')
    readonly_fields = (
        'message_id', 'thread_id', 'sender_id', 'recipient_id',
        'timestamp', 'synced_at', 'is_within_24h_window'
    )
    
    fieldsets = (
        ('Сообщение', {
            'fields': (
                'account', 'thread_id', 'text', 'attachments', 'message_type'
            )
        }),
        ('Участники', {
            'fields': ('sender_id', 'sender_username', 'recipient_id', 'direction')
        }),
        ('Статус', {
            'fields': (
                'is_read', 'is_bot_response', 'is_within_24h_window'
            )
        }),
        ('Instagram API', {
            'fields': ('message_id', 'timestamp', 'synced_at'),
            'classes': ('collapse',)
        })
    )
    
    def text_preview(self, obj):
        if not obj.text:
            return f'({obj.message_type})'
        preview = (obj.text[:60] + '...') if len(obj.text) > 60 else obj.text
        return preview
    text_preview.short_description = 'Сообщение'


@admin.register(IGWebhookEvent)
class IGWebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        'kind', 'object_id', 'account', 'processed', 
        'retry_count', 'delivered_at'
    )
    list_filter = ('kind', 'processed', 'account')
    search_fields = ('object_id', 'error_message')
    readonly_fields = (
        'raw_payload', 'delivered_at', 'processed_at'
    )
    
    fieldsets = (
        ('Событие', {
            'fields': ('account', 'kind', 'object_id')
        }),
        ('Обработка', {
            'fields': ('processed', 'processed_at', 'error_message', 'retry_count')
        }),
        ('Данные', {
            'fields': ('raw_payload', 'delivered_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['reprocess_events']
    
    def reprocess_events(self, request, queryset):
        from .tasks import process_webhook_event
        count = 0
        for event in queryset:
            process_webhook_event.delay(event.id)
            count += 1
        self.message_user(request, f'Поставлено на повторную обработку: {count} событий')
    reprocess_events.short_description = 'Повторно обработать события'


@admin.register(IGDMTemplate)
class IGDMTemplateAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'account', 'trigger_type', 'enabled', 
        'include_coupon', 'usage_count', 'priority'
    )
    list_filter = ('enabled', 'trigger_type', 'include_coupon', 'account')
    search_fields = ('name', 'trigger_keywords', 'response_text')
    
    fieldsets = (
        ('Шаблон', {
            'fields': ('account', 'name', 'enabled', 'priority')
        }),
        ('Триггер', {
            'fields': ('trigger_type', 'trigger_keywords')
        }),
        ('Ответ', {
            'fields': ('response_text', 'include_coupon', 'coupon_campaign')
        }),
        ('Статистика', {
            'fields': ('usage_count',),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('account', 'coupon_campaign')
