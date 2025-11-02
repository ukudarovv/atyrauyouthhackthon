"""
Модели для интеграции с Instagram Business API
"""
import json
from datetime import datetime, timedelta
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.businesses.models import Business


class IGAccountStatus(models.TextChoices):
    CONNECTED = 'connected', 'Connected'
    EXPIRED = 'expired', 'Token Expired'
    REVOKED = 'revoked', 'Access Revoked'
    ERROR = 'error', 'Error'


class IGAccount(models.Model):
    """
    Instagram Business аккаунт, подключенный к бизнесу
    """
    business = models.OneToOneField(
        Business, 
        on_delete=models.CASCADE, 
        related_name='ig_account'
    )
    
    # Instagram Graph API данные
    ig_user_id = models.CharField(max_length=50, unique=True)
    page_id = models.CharField(max_length=50)  # связанная Facebook Page
    username = models.CharField(max_length=100)
    profile_picture_url = models.URLField(blank=True)
    followers_count = models.PositiveIntegerField(default=0)
    
    # Токены и права доступа
    access_token_encrypted = models.TextField()  # зашифрованный long-lived token
    token_expires_at = models.DateTimeField()
    permissions = models.JSONField(default=list)  # список разрешений
    
    # Статус и метаданные
    status = models.CharField(
        max_length=20, 
        choices=IGAccountStatus.choices, 
        default=IGAccountStatus.CONNECTED
    )
    connected_at = models.DateTimeField(auto_now_add=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    sync_errors = models.JSONField(default=list)
    
    # Настройки
    auto_publish_enabled = models.BooleanField(default=True)
    dm_bot_enabled = models.BooleanField(default=True)
    comment_moderation_enabled = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = 'Instagram Account'
        verbose_name_plural = 'Instagram Accounts'
        indexes = [
            models.Index(fields=['ig_user_id']),
            models.Index(fields=['business', 'status']),
        ]
    
    def __str__(self):
        return f"@{self.username} ({self.business.name})"
    
    @property
    def is_token_expired(self):
        """Проверяет, истек ли токен"""
        return timezone.now() >= self.token_expires_at
    
    @property
    def days_until_expiry(self):
        """Количество дней до истечения токена"""
        if self.is_token_expired:
            return 0
        return (self.token_expires_at - timezone.now()).days
    
    @property
    def needs_refresh(self):
        """Нужно ли обновлять токен (осталось меньше 7 дней)"""
        return self.days_until_expiry <= 7
    
    def get_access_token(self):
        """Получает расшифрованный токен доступа"""
        # TODO: Реализовать расшифровку токена
        # Пока возвращаем как есть для разработки
        return self.access_token_encrypted
    
    def set_access_token(self, token):
        """Устанавливает зашифрованный токен доступа"""
        # TODO: Реализовать шифрование токена
        # Пока сохраняем как есть для разработки
        self.access_token_encrypted = token


class IGMediaType(models.TextChoices):
    PHOTO = 'photo', 'Photo'
    VIDEO = 'video', 'Video'
    REEL = 'reel', 'Reel'
    CAROUSEL = 'carousel', 'Carousel Album'


class IGMediaStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    SCHEDULED = 'scheduled', 'Scheduled'
    PUBLISHING = 'publishing', 'Publishing'
    PUBLISHED = 'published', 'Published'
    FAILED = 'failed', 'Failed'


class IGMedia(models.Model):
    """
    Instagram медиа контент (посты, reels, карусели)
    """
    account = models.ForeignKey(
        IGAccount, 
        on_delete=models.CASCADE, 
        related_name='media'
    )
    
    # Instagram API данные
    ig_media_id = models.CharField(max_length=50, blank=True, db_index=True)
    creation_id = models.CharField(max_length=50, blank=True)  # container ID
    permalink = models.URLField(blank=True)
    
    # Контент
    media_type = models.CharField(max_length=20, choices=IGMediaType.choices)
    caption = models.TextField(blank=True)
    media_url = models.URLField()  # основное изображение/видео
    thumbnail_url = models.URLField(blank=True)  # превью для видео
    children_data = models.JSONField(default=list)  # для каруселей
    
    # Статус и планирование
    status = models.CharField(
        max_length=20, 
        choices=IGMediaStatus.choices, 
        default=IGMediaStatus.DRAFT
    )
    publish_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    
    # UTM и аналитика
    utm_source = models.CharField(max_length=50, default='ig')
    utm_medium = models.CharField(max_length=50, default='social')
    utm_campaign = models.CharField(max_length=100, blank=True)
    utm_content = models.CharField(max_length=100, blank=True)
    utm_term = models.CharField(max_length=100, blank=True)
    
    # Метрики (кэшированные из Insights API)
    reach = models.PositiveIntegerField(default=0)
    impressions = models.PositiveIntegerField(default=0)
    likes = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)
    saves = models.PositiveIntegerField(default=0)
    shares = models.PositiveIntegerField(default=0)
    plays = models.PositiveIntegerField(default=0)  # для видео/reels
    
    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_insights_sync = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    class Meta:
        verbose_name = 'Instagram Media'
        verbose_name_plural = 'Instagram Media'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', 'status']),
            models.Index(fields=['ig_media_id']),
            models.Index(fields=['publish_at']),
            models.Index(fields=['utm_campaign']),
        ]
    
    def __str__(self):
        caption_preview = (self.caption[:50] + '...') if len(self.caption) > 50 else self.caption
        return f"{self.get_media_type_display()}: {caption_preview}"
    
    @property
    def is_scheduled(self):
        """Проверяет, запланирован ли пост на будущее"""
        return (
            self.status == IGMediaStatus.SCHEDULED and 
            self.publish_at and 
            self.publish_at > timezone.now()
        )
    
    @property
    def is_due_for_publishing(self):
        """Проверяет, пора ли публиковать"""
        return (
            self.status == IGMediaStatus.SCHEDULED and
            self.publish_at and 
            self.publish_at <= timezone.now()
        )
    
    @property
    def utm_params(self):
        """Возвращает UTM параметры как словарь"""
        return {
            'utm_source': self.utm_source,
            'utm_medium': self.utm_medium,
            'utm_campaign': self.utm_campaign,
            'utm_content': self.utm_content or self.ig_media_id,
            'utm_term': self.utm_term,
        }
    
    @property
    def engagement_rate(self):
        """Вычисляет engagement rate (если есть данные)"""
        if not self.impressions:
            return 0
        engagements = self.likes + self.comments_count + self.saves + self.shares
        return round((engagements / self.impressions) * 100, 2)


class IGComment(models.Model):
    """
    Комментарии к Instagram медиа
    """
    media = models.ForeignKey(
        IGMedia, 
        on_delete=models.CASCADE, 
        related_name='comments'
    )
    
    # Instagram API данные
    ig_comment_id = models.CharField(max_length=50, unique=True, db_index=True)
    ig_parent_id = models.CharField(max_length=50, blank=True)  # для ответов
    
    # Контент
    text = models.TextField()
    author_username = models.CharField(max_length=100)
    author_id = models.CharField(max_length=50, blank=True)
    
    # Модерация
    hidden = models.BooleanField(default=False)
    moderated_by = models.ForeignKey(
        'accounts.User', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL,
        related_name='moderated_ig_comments'
    )
    moderated_at = models.DateTimeField(null=True, blank=True)
    moderation_action = models.CharField(max_length=20, blank=True)  # hide, reply, delete
    
    # AI анализ (интеграция с Этапом 12)
    ai_sentiment = models.SmallIntegerField(null=True, blank=True)  # -100..100
    ai_toxic = models.BooleanField(default=False)
    ai_labels = models.JSONField(default=list)
    ai_summary = models.CharField(max_length=280, blank=True)
    
    # Метаданные
    created_at = models.DateTimeField()  # время создания в Instagram
    synced_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Instagram Comment'
        verbose_name_plural = 'Instagram Comments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['media', 'created_at']),
            models.Index(fields=['ig_comment_id']),
            models.Index(fields=['author_username']),
            models.Index(fields=['ai_toxic', 'hidden']),
        ]
    
    def __str__(self):
        text_preview = (self.text[:50] + '...') if len(self.text) > 50 else self.text
        return f"@{self.author_username}: {text_preview}"


class IGThreadMessage(models.Model):
    """
    Сообщения в Instagram Direct Messages
    """
    account = models.ForeignKey(
        IGAccount, 
        on_delete=models.CASCADE, 
        related_name='dm_messages'
    )
    
    # Instagram API данные
    thread_id = models.CharField(max_length=100, db_index=True)
    message_id = models.CharField(max_length=100, unique=True, db_index=True)
    
    # Участники диалога
    sender_id = models.CharField(max_length=50)
    sender_username = models.CharField(max_length=100, blank=True)
    recipient_id = models.CharField(max_length=50)
    
    # Контент
    text = models.TextField(blank=True)
    attachments = models.JSONField(default=list)  # изображения, стикеры и т.д.
    message_type = models.CharField(max_length=20, default='text')  # text, image, sticker, etc.
    
    # Направление и статус
    direction = models.CharField(max_length=10, choices=[
        ('in', 'Incoming'),
        ('out', 'Outgoing')
    ])
    is_read = models.BooleanField(default=False)
    is_bot_response = models.BooleanField(default=False)
    
    # 24-часовое окно для промо-контента
    is_within_24h_window = models.BooleanField(default=False)
    
    # Метаданные
    timestamp = models.DateTimeField()  # время создания в Instagram
    synced_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Instagram DM'
        verbose_name_plural = 'Instagram DMs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['account', 'thread_id', 'timestamp']),
            models.Index(fields=['message_id']),
            models.Index(fields=['direction', 'is_read']),
        ]
    
    def __str__(self):
        direction_icon = '📨' if self.direction == 'in' else '📤'
        text_preview = (self.text[:30] + '...') if len(self.text) > 30 else self.text
        return f"{direction_icon} @{self.sender_username}: {text_preview}"


class IGWebhookEventKind(models.TextChoices):
    COMMENT = 'comment', 'Comment'
    MESSAGE = 'message', 'Message'  
    MENTION = 'mention', 'Mention'
    MEDIA_STATUS = 'media_status', 'Media Status Change'
    ACCOUNT_UPDATE = 'account_update', 'Account Update'


class IGWebhookEvent(models.Model):
    """
    Лог событий от Instagram Webhooks
    """
    account = models.ForeignKey(
        IGAccount,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='webhook_events'
    )
    
    # Webhook данные
    kind = models.CharField(max_length=20, choices=IGWebhookEventKind.choices)
    raw_payload = models.JSONField()  # полные данные от webhook
    object_id = models.CharField(max_length=50, blank=True)  # ID комментария/сообщения/медиа
    
    # Обработка
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    
    # Метаданные
    delivered_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Instagram Webhook Event'
        verbose_name_plural = 'Instagram Webhook Events'
        ordering = ['-delivered_at']
        indexes = [
            models.Index(fields=['kind', 'processed']),
            models.Index(fields=['account', 'delivered_at']),
            models.Index(fields=['object_id']),
        ]
    
    def __str__(self):
        return f"{self.get_kind_display()}: {self.object_id} ({self.delivered_at.strftime('%Y-%m-%d %H:%M')})"


class IGDMTemplate(models.Model):
    """
    Шаблоны для автоответов в DM
    """
    account = models.ForeignKey(
        IGAccount,
        on_delete=models.CASCADE,
        related_name='dm_templates'
    )
    
    # Правило срабатывания
    name = models.CharField(max_length=100)
    trigger_keywords = models.JSONField(default=list)  # ключевые слова
    trigger_type = models.CharField(max_length=20, choices=[
        ('contains', 'Contains keyword'),
        ('equals', 'Exact match'),
        ('starts_with', 'Starts with'),
        ('regex', 'Regular expression')
    ], default='contains')
    
    # Ответ
    response_text = models.TextField()
    include_coupon = models.BooleanField(default=False)
    coupon_campaign = models.ForeignKey(
        'campaigns.Campaign',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='ig_dm_templates'
    )
    
    # Настройки
    enabled = models.BooleanField(default=True)
    priority = models.PositiveSmallIntegerField(default=10)  # чем меньше, тем выше приоритет
    usage_count = models.PositiveIntegerField(default=0)
    
    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Instagram DM Template'
        verbose_name_plural = 'Instagram DM Templates'
        ordering = ['priority', 'name']
        indexes = [
            models.Index(fields=['account', 'enabled']),
            models.Index(fields=['priority']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.account.username})"
    
    def matches_message(self, text):
        """Проверяет, соответствует ли сообщение шаблону"""
        if not self.enabled or not text:
            return False
        
        text_lower = text.lower()
        
        for keyword in self.trigger_keywords:
            keyword_lower = keyword.lower()
            
            if self.trigger_type == 'contains' and keyword_lower in text_lower:
                return True
            elif self.trigger_type == 'equals' and text_lower == keyword_lower:
                return True
            elif self.trigger_type == 'starts_with' and text_lower.startswith(keyword_lower):
                return True
            elif self.trigger_type == 'regex':
                import re
                try:
                    if re.search(keyword, text, re.IGNORECASE):
                        return True
                except re.error:
                    continue
        
        return False
