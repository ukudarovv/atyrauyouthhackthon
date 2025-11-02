from django.db import models
from django.conf import settings


class WalletPassKind(models.TextChoices):
    GOOGLE = 'google', 'Google Wallet'
    APPLE = 'apple', 'Apple Wallet'


class WalletPassStatus(models.TextChoices):
    CREATED = 'created', 'Created'
    ACTIVE = 'active', 'Active'
    EXPIRED = 'expired', 'Expired'
    DELETED = 'deleted', 'Deleted'


class WalletPass(models.Model):
    """Представляет карту в Google/Apple Wallet"""
    business = models.ForeignKey('businesses.Business', on_delete=models.CASCADE, related_name='wallet_passes')
    coupon = models.ForeignKey('coupons.Coupon', on_delete=models.CASCADE, related_name='wallet_passes', null=True, blank=True)
    campaign = models.ForeignKey('campaigns.Campaign', on_delete=models.CASCADE, related_name='wallet_passes', null=True, blank=True)
    
    # Идентификация клиента
    customer_phone = models.CharField(max_length=32)
    customer_email = models.EmailField(blank=True)
    
    # Платформа и идентификаторы
    platform = models.CharField(max_length=10, choices=WalletPassKind.choices)
    class_id = models.CharField(max_length=255)  # Google: issuer.classId, Apple: passTypeId
    object_id = models.CharField(max_length=255, unique=True)  # Google: issuer.objectId, Apple: serialNumber
    
    # Содержимое карты
    title = models.CharField(max_length=100, default='Скидочная карта')
    subtitle = models.CharField(max_length=100, blank=True)
    barcode_value = models.CharField(max_length=100)  # Код купона/QR
    
    # Статус
    status = models.CharField(max_length=10, choices=WalletPassStatus.choices, default=WalletPassStatus.CREATED)
    
    # Временные рамки
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    
    # Уведомления
    notification_sent_24h = models.BooleanField(default=False)
    notification_sent_1h = models.BooleanField(default=False)
    
    # Мета-данные
    metadata = models.JSONField(default=dict, blank=True)  # Дополнительные данные для провайдера
    
    # Growth механики
    streak_data = models.JSONField(default=dict, blank=True, help_text="Данные серий посещений")
    
    # Даты
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', 'created_at']),
            models.Index(fields=['customer_phone']),
            models.Index(fields=['platform', 'status']),
            models.Index(fields=['valid_until']),
        ]
    
    def __str__(self):
        return f'{self.get_platform_display()} pass for {self.customer_phone}'


class WalletClass(models.Model):
    """Представляет класс карт в Google/Apple Wallet"""
    business = models.ForeignKey('businesses.Business', on_delete=models.CASCADE, related_name='wallet_classes')
    platform = models.CharField(max_length=10, choices=WalletPassKind.choices)
    class_id = models.CharField(max_length=255, unique=True)
    
    # Настройки класса
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    # Визуальное оформление
    background_color = models.CharField(max_length=7, default='#111827')  # HEX цвет
    logo_url = models.URLField(blank=True)
    hero_image_url = models.URLField(blank=True)
    
    # Локации для Nearby уведомлений
    locations = models.JSONField(default=list, blank=True)  # [{"lat": 43.23, "lng": 76.88, "name": "Coffee Fox"}]
    
    # Статус в провайдере
    review_status = models.CharField(max_length=20, default='UNDER_REVIEW')
    is_active = models.BooleanField(default=True)
    
    # Мета-данные
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['business', 'platform']
        indexes = [
            models.Index(fields=['platform', 'is_active']),
        ]
    
    def __str__(self):
        return f'{self.get_platform_display()} class: {self.name}'
