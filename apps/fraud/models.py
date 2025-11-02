from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.businesses.models import Business
from apps.coupons.models import Coupon

class RiskKind(models.TextChoices):
    ISSUE = 'issue', 'Issue'
    REDEEM = 'redeem', 'Redeem'

class RiskDecision(models.TextChoices):
    ALLOW = 'allow', 'Allow'
    WARN = 'warn', 'Warn'
    BLOCK = 'block', 'Block'

class RiskEvent(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='risk_events')
    kind = models.CharField(max_length=12, choices=RiskKind.choices)
    campaign_id = models.IntegerField(null=True, blank=True)
    coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.SET_NULL, related_name='risk_events')

    phone = models.CharField(max_length=32, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    ua = models.TextField(blank=True)
    utm = models.JSONField(default=dict, blank=True)

    score = models.IntegerField(default=0)
    reasons = models.JSONField(default=list, blank=True)  # список строк с весами, напр. ["ip_many_1h:+20 (24)"]
    decision = models.CharField(max_length=10, choices=RiskDecision.choices, default=RiskDecision.ALLOW)
    resolved = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', 'created_at']),
            models.Index(fields=['phone']),
            models.Index(fields=['ip']),
            models.Index(fields=['kind']),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.score} {self.get_decision_display()} ({self.created_at:%Y-%m-%d %H:%M})"
