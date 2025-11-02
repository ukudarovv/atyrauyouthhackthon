from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import URLValidator
import secrets


class ContactPointType(models.TextChoices):
    EMAIL = 'email', 'Email'
    SMS = 'sms', 'SMS'
    WHATSAPP = 'whatsapp', 'WhatsApp'
    TELEGRAM = 'telegram', 'Telegram'
    INSTAGRAM = 'instagram', 'Instagram DM'
    WALLET = 'wallet', 'Wallet Push'


class ContactPoint(models.Model):
    """Точка контакта с клиентом"""
    business = models.ForeignKey('businesses.Business', on_delete=models.CASCADE, related_name='contact_points')
    customer = models.ForeignKey('customers.Customer', on_delete=models.CASCADE, related_name='contact_points', null=True, blank=True)
    
    # Тип и значение контакта
    type = models.CharField(max_length=12, choices=ContactPointType.choices)
    value = models.CharField(max_length=255)  # email, phone, telegram_id, etc.
    
    # Статус и настройки
    verified = models.BooleanField(default=False)
    opt_in = models.BooleanField(default=True)  # согласие на получение сообщений
    
    # Метрики
    last_seen_at = models.DateTimeField(null=True, blank=True)
    cost_weight = models.DecimalField(max_digits=8, decimal_places=4, default=1.0)  # вес стоимости канала
    
    # Мета-данные
    metadata = models.JSONField(default=dict, blank=True)  # дополнительные данные (telegram_username, etc.)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['business', 'type', 'value']
        indexes = [
            models.Index(fields=['business', 'type']),
            models.Index(fields=['customer', 'type']),
            models.Index(fields=['type', 'verified', 'opt_in']),
        ]
    
    def __str__(self):
        return f'{self.get_type_display()}: {self.value}'


class MessageTemplate(models.Model):
    """Шаблон сообщения для определенного канала"""
    business = models.ForeignKey('businesses.Business', on_delete=models.CASCADE, related_name='message_templates')
    
    # Идентификация
    name = models.CharField(max_length=100)
    channel = models.CharField(max_length=12, choices=ContactPointType.choices)
    locale = models.CharField(max_length=5, default='ru')  # ru, kz, en
    
    # Содержимое
    subject = models.CharField(max_length=200, blank=True)  # для email
    body_text = models.TextField()  # основное содержание
    body_html = models.TextField(blank=True)  # HTML версия для email
    
    # Переменные и персонализация
    variables = models.JSONField(default=list, blank=True)  # список доступных переменных
    
    # A/B тестирование
    a_b_bucket = models.CharField(max_length=1, choices=[('A', 'A'), ('B', 'B')], blank=True)
    
    # Мета-данные
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['business', 'channel', 'locale']),
            models.Index(fields=['channel', 'is_active']),
        ]
    
    def __str__(self):
        return f'{self.name} ({self.get_channel_display()})'


class BlastStatus(models.TextChoices):
    DRAFT = 'draft', 'Черновик'
    SCHEDULED = 'scheduled', 'Запланирована'
    RUNNING = 'running', 'Выполняется'
    COMPLETED = 'completed', 'Завершена'
    PAUSED = 'paused', 'Приостановлена'
    CANCELLED = 'cancelled', 'Отменена'


class BlastTrigger(models.TextChoices):
    MANUAL = 'manual', 'Ручной запуск'
    SCHEDULED = 'scheduled', 'По расписанию'
    EVENT_COUPON_ISSUED = 'event_coupon_issued', 'Выдан купон'
    EVENT_COUPON_REDEEMED = 'event_coupon_redeemed', 'Погашен купон'
    EVENT_REVIEW_TOXIC = 'event_review_toxic', 'Токсичный отзыв'
    EVENT_SEGMENT_ENTER = 'event_segment_enter', 'Вход в сегмент'
    EXPIRY_24H = 'expiry_24h', 'Истекает через 24ч'
    EXPIRY_1H = 'expiry_1h', 'Истекает через 1ч'


class Blast(models.Model):
    """Рассылка (массовая или триггерная)"""
    business = models.ForeignKey('businesses.Business', on_delete=models.CASCADE, related_name='blasts')
    
    # Основная информация
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Тип и триггеры
    trigger = models.CharField(max_length=25, choices=BlastTrigger.choices, default=BlastTrigger.MANUAL)
    status = models.CharField(max_length=12, choices=BlastStatus.choices, default=BlastStatus.DRAFT)
    
    # Аудитория
    segment = models.ForeignKey('segments.Segment', on_delete=models.SET_NULL, null=True, blank=True)
    custom_filter = models.JSONField(default=dict, blank=True)  # дополнительные фильтры
    
    # Стратегия отправки
    strategy = models.JSONField(default=dict, blank=True)  # каскад каналов, тайминги, лимиты
    
    # Планирование
    schedule_at = models.DateTimeField(null=True, blank=True)
    
    # Бюджет и лимиты
    budget_cap = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    current_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Метрики
    total_recipients = models.IntegerField(default=0)
    sent_count = models.IntegerField(default=0)
    delivered_count = models.IntegerField(default=0)
    opened_count = models.IntegerField(default=0)
    clicked_count = models.IntegerField(default=0)
    converted_count = models.IntegerField(default=0)  # выдачи/погашения купонов
    
    # Даты
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', 'status']),
            models.Index(fields=['trigger', 'status']),
            models.Index(fields=['schedule_at']),
        ]
    
    def __str__(self):
        return f'{self.name} ({self.get_status_display()})'
    
    def can_start(self):
        """Проверяет можно ли запустить рассылку"""
        return self.status in [BlastStatus.DRAFT, BlastStatus.SCHEDULED]
    
    def conversion_rate(self):
        """Конверсия: клики -> конверсии"""
        if self.clicked_count > 0:
            return (self.converted_count / self.clicked_count) * 100
        return 0
    
    def delivery_rate(self):
        """Доставляемость"""
        if self.sent_count > 0:
            return (self.delivered_count / self.sent_count) * 100
        return 0


class BlastRecipientStatus(models.TextChoices):
    PENDING = 'pending', 'Ожидает'
    PROCESSING = 'processing', 'Обрабатывается'
    COMPLETED = 'completed', 'Завершен'
    FAILED = 'failed', 'Неудачно'
    SKIPPED = 'skipped', 'Пропущен'


class BlastRecipient(models.Model):
    """Получатель в рассылке"""
    blast = models.ForeignKey(Blast, on_delete=models.CASCADE, related_name='recipients')
    customer = models.ForeignKey('customers.Customer', on_delete=models.CASCADE, related_name='blast_recipients')
    
    # Контактные точки для каскада
    contact_points = models.JSONField(default=list)  # список ID контактных точек в порядке приоритета
    
    # Статус выполнения
    status = models.CharField(max_length=12, choices=BlastRecipientStatus.choices, default=BlastRecipientStatus.PENDING)
    current_step = models.IntegerField(default=0)  # текущий шаг в каскаде
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    
    # Метрики
    attempts_count = models.IntegerField(default=0)
    last_opened_at = models.DateTimeField(null=True, blank=True)
    last_clicked_at = models.DateTimeField(null=True, blank=True)
    converted_at = models.DateTimeField(null=True, blank=True)
    
    # Стоимость
    total_cost = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['blast', 'customer']
        indexes = [
            models.Index(fields=['blast', 'status']),
            models.Index(fields=['status', 'next_attempt_at']),
        ]
    
    def __str__(self):
        return f'{self.blast.name} -> {self.customer.phone_e164}'


class DeliveryStatus(models.TextChoices):
    QUEUED = 'queued', 'В очереди'
    SENT = 'sent', 'Отправлено'
    DELIVERED = 'delivered', 'Доставлено'
    OPENED = 'opened', 'Открыто'
    CLICKED = 'clicked', 'Клик'
    FAILED = 'failed', 'Неудачно'
    BOUNCED = 'bounced', 'Отклонено'
    UNSUBSCRIBED = 'unsubscribed', 'Отписка'


class DeliveryAttempt(models.Model):
    """Попытка доставки сообщения"""
    blast_recipient = models.ForeignKey(BlastRecipient, on_delete=models.CASCADE, related_name='delivery_attempts')
    contact_point = models.ForeignKey(ContactPoint, on_delete=models.CASCADE, related_name='delivery_attempts')
    
    # Провайдер и канал
    channel = models.CharField(max_length=12, choices=ContactPointType.choices)
    provider = models.CharField(max_length=50)  # sendgrid, twilio, etc.
    
    # Содержимое
    template = models.ForeignKey(MessageTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    
    # Статус и результат
    status = models.CharField(max_length=15, choices=DeliveryStatus.choices, default=DeliveryStatus.QUEUED)
    external_id = models.CharField(max_length=100, blank=True)  # ID сообщения у провайдера
    
    # Метрики времени
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    
    # Стоимость и ошибки
    cost = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    error_message = models.TextField(blank=True)
    
    # Мета-данные
    metadata = models.JSONField(default=dict, blank=True)  # webhook data, etc.
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['blast_recipient', 'status']),
            models.Index(fields=['channel', 'status']),
            models.Index(fields=['external_id']),
            models.Index(fields=['sent_at']),
        ]
    
    def __str__(self):
        return f'{self.get_channel_display()} -> {self.contact_point.value} ({self.get_status_display()})'


class ShortLink(models.Model):
    """Короткие ссылки для трекинга переходов"""
    business = models.ForeignKey('businesses.Business', on_delete=models.CASCADE, related_name='short_links')
    
    # Основная информация
    short_code = models.CharField(max_length=8, unique=True, db_index=True)
    original_url = models.URLField(validators=[URLValidator()])
    
    # Связь с рассылкой
    blast = models.ForeignKey(Blast, on_delete=models.CASCADE, related_name='short_links', null=True, blank=True)
    delivery_attempt = models.ForeignKey(DeliveryAttempt, on_delete=models.SET_NULL, null=True, blank=True)
    
    # UTM параметры
    utm_source = models.CharField(max_length=50, blank=True)
    utm_medium = models.CharField(max_length=50, blank=True)
    utm_campaign = models.CharField(max_length=100, blank=True)
    utm_content = models.CharField(max_length=100, blank=True)
    
    # Метрики
    clicks_count = models.IntegerField(default=0)
    unique_clicks_count = models.IntegerField(default=0)
    
    # Настройки
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['business', 'blast']),
            models.Index(fields=['short_code']),
        ]
    
    def __str__(self):
        return f'{self.short_code} -> {self.original_url[:50]}'
    
    @staticmethod
    def generate_code():
        """Генерирует уникальный короткий код"""
        return secrets.token_urlsafe(6)[:8]
    
    def get_short_url(self):
        """Возвращает полный короткий URL"""
        from django.conf import settings
        base_url = getattr(settings, 'SHORT_LINK_BASE_URL', 'https://yoursite.com')
        return f'{base_url}/s/{self.short_code}'


class ShortLinkClick(models.Model):
    """Клик по короткой ссылке"""
    short_link = models.ForeignKey(ShortLink, on_delete=models.CASCADE, related_name='clicks')
    
    # Информация о клике
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    referer = models.URLField(blank=True)
    
    # Геолокация и устройство
    country = models.CharField(max_length=2, blank=True)  # ISO код страны
    device_type = models.CharField(max_length=20, blank=True)  # mobile, desktop, tablet
    
    # Уникальность
    fingerprint = models.CharField(max_length=32, blank=True)  # hash для определения уникальности
    
    clicked_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['short_link', 'clicked_at']),
            models.Index(fields=['fingerprint']),
        ]
    
    def __str__(self):
        return f'Click on {self.short_link.short_code} at {self.clicked_at}'


class MessagePreference(models.Model):
    """Предпочтения клиента по сообщениям"""
    business = models.ForeignKey('businesses.Business', on_delete=models.CASCADE, related_name='message_preferences')
    customer = models.ForeignKey('customers.Customer', on_delete=models.CASCADE, related_name='message_preferences')
    
    # Предпочтительные каналы (в порядке приоритета)
    preferred_channels = models.JSONField(default=list)  # ['whatsapp', 'sms', 'email']
    
    # Время для отправки
    quiet_hours_start = models.TimeField(default='21:00')
    quiet_hours_end = models.TimeField(default='09:00')
    timezone = models.CharField(max_length=50, default='Asia/Almaty')
    
    # Настройки языка
    locale = models.CharField(max_length=5, default='ru')
    
    # Частота сообщений
    max_messages_per_day = models.IntegerField(default=3)
    max_messages_per_week = models.IntegerField(default=10)
    
    # Подписки на типы сообщений
    allow_promotional = models.BooleanField(default=True)
    allow_transactional = models.BooleanField(default=True)
    allow_expiry_reminders = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['business', 'customer']
        indexes = [
            models.Index(fields=['business', 'customer']),
        ]
    
    def __str__(self):
        return f'Preferences for {self.customer.phone_e164}'
