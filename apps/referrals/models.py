from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.businesses.models import Business
from apps.campaigns.models import Campaign
import secrets

User = settings.AUTH_USER_MODEL

class CustomerSource(models.TextChoices):
    QR = 'qr', 'QR'
    LANDING = 'landing', 'Landing'
    IMPORT = 'import', 'Import'
    REFERRAL = 'referral', 'Referral'

class Customer(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='customers')
    phone = models.CharField(max_length=32, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    name = models.CharField(max_length=160, blank=True)
    consent_marketing = models.BooleanField(default=False)
    source = models.CharField(max_length=20, choices=CustomerSource.choices, default=CustomerSource.LANDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['business', 'phone'])]

    def __str__(self):
        return self.name or self.phone or f"Customer#{self.pk}"

class RewardStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    GRANTED = 'granted', 'Granted'
    REJECTED = 'rejected', 'Rejected'

class Referral(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='referrals')
    referrer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='referrals_made')
    token = models.CharField(max_length=24, unique=True, db_index=True)
    referee = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='referred_by')
    reward_status = models.CharField(max_length=16, choices=RewardStatus.choices, default=RewardStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['business','created_at'])]

    def __str__(self):
        return f"{self.token} ({self.business.name})"

    @staticmethod
    def gen_token() -> str:
        return secrets.token_urlsafe(9)  # компактно и уникально