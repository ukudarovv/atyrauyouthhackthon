from django.db import models
from django.utils import timezone
from django.conf import settings
import secrets

from apps.campaigns.models import Campaign

class CouponStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    REDEEMED = 'redeemed', 'Redeemed'
    EXPIRED = 'expired', 'Expired'

class Coupon(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='coupons')
    code = models.CharField(max_length=16, unique=True, db_index=True)
    phone = models.CharField(max_length=32, blank=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=CouponStatus.choices, default=CouponStatus.ACTIVE)

    # для будущих сценариев
    uses_count = models.PositiveIntegerField(default=0)
    max_uses = models.PositiveIntegerField(default=1)
    
    # антифрод поля
    risk_score = models.IntegerField(default=0)
    risk_flag = models.BooleanField(default=False)  # если был warn/block при выдаче
    metadata = models.JSONField(default=dict, blank=True)  # здесь храним ip/ua/utm при выдаче

    class Meta:
        ordering = ['-issued_at']
        indexes = [models.Index(fields=['campaign', 'issued_at'])]

    def __str__(self):
        return f"{self.code} ({self.campaign.name})"

    @staticmethod
    def generate_code() -> str:
        """Генерирует 8-символьный уникальный код"""
        return secrets.token_hex(4).upper()

    def is_expired(self) -> bool:
        """Проверяет истек ли срок действия купона"""
        return bool(self.expires_at and timezone.now() > self.expires_at)

    def is_active(self) -> bool:
        """Проверяет активен ли купон и можно ли его использовать"""
        if self.status != CouponStatus.ACTIVE:
            return False
        if self.is_expired():
            return False
        if self.uses_count >= self.max_uses:
            return False
        return True