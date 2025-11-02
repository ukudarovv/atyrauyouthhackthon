from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.coupons.models import Coupon

User = settings.AUTH_USER_MODEL

class Redemption(models.Model):
    """Запись о погашении купона"""
    coupon = models.OneToOneField(Coupon, on_delete=models.PROTECT, related_name='redemption')
    cashier = models.ForeignKey(User, on_delete=models.PROTECT, related_name='redemptions')
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Сумма чека")
    note = models.CharField(max_length=255, blank=True, help_text="Комментарий кассира")
    pos_ref = models.CharField(max_length=64, blank=True, help_text="Номер чека/операции")
    redeemed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-redeemed_at']
        indexes = [models.Index(fields=['redeemed_at'])]

    def __str__(self):
        return f"{self.coupon.code} / {self.redeemed_at:%Y-%m-%d %H:%M}"