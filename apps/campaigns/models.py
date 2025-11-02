from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from slugify import slugify
from apps.businesses.models import Business, Location

User = settings.AUTH_USER_MODEL

class CampaignType(models.TextChoices):
    COUPON = 'coupon', 'Coupon'
    REFERRAL = 'referral', 'Referral'
    REVIEW = 'review', 'Review'

class Campaign(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='campaigns')
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name='campaigns')
    type = models.CharField(max_length=16, choices=CampaignType.choices, default=CampaignType.COUPON)

    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True, blank=True)

    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    description = models.TextField(blank=True)
    terms = models.TextField(blank=True)
    landing_theme = models.CharField(max_length=50, default='default')

    # Лимиты для купонов
    issue_limit = models.PositiveIntegerField(default=100, help_text="Сколько купонов можно выдать")
    per_phone_limit = models.PositiveIntegerField(default=1, help_text="Сколько купонов на 1 номер")

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']
        indexes = [models.Index(fields=['slug']), models.Index(fields=['created_at'])]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(f"{self.business.name}-{self.name}") or "camp"
            slug = base
            i = 1
            # избегаем циклического импорта при миграциях
            while Campaign.objects.filter(slug=slug).exists():
                i += 1
                slug = f"{base}-{i}"
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.business.name})"

    def get_public_url(self):
        return reverse('campaigns:landing_public', args=[self.slug])

    def is_running_now(self) -> bool:
        if not self.is_active:
            return False
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True

    def issued_count(self) -> int:
        """Количество выданных купонов"""
        # Избегаем циклический импорт
        try:
            from apps.coupons.models import Coupon
            return Coupon.objects.filter(campaign=self).count()
        except ImportError:
            return 0

    def remaining(self) -> int:
        """Количество оставшихся купонов"""
        return max(0, self.issue_limit - self.issued_count())

class Landing(models.Model):
    campaign = models.OneToOneField(Campaign, on_delete=models.CASCADE, related_name='landing')
    headline = models.CharField(max_length=200)
    body_md = models.TextField(blank=True)
    cta_text = models.CharField(max_length=60, default='Получить предложение')
    hero_image = models.ImageField(upload_to='landing_hero/', null=True, blank=True)

    seo_title = models.CharField(max_length=70, blank=True)
    seo_desc = models.CharField(max_length=160, blank=True)
    og_image = models.ImageField(upload_to='og/', null=True, blank=True)

    primary_color = models.CharField(max_length=7, default='#111827')  # #RRGGBB

    def __str__(self):
        return f"Landing: {self.campaign.name}"

class TrackEventType(models.TextChoices):
    LANDING_VIEW = 'landing_view', 'Landing View'
    LANDING_CLICK = 'landing_click', 'Landing Click'
    COUPON_ISSUE = 'coupon_issue', 'Coupon Issue'
    COUPON_REDEEM = 'coupon_redeem', 'Coupon Redeem'
    REFERRAL_CLICK = 'referral_click', 'Referral Click'
    REVIEW_SUBMIT = 'review_submit', 'Review Submit'

class TrackEvent(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='events')
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='events', null=True, blank=True)
    type = models.CharField(max_length=32, choices=TrackEventType.choices)
    utm = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    ua = models.TextField(blank=True)
    referer = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['campaign', 'created_at'])]
        ordering = ['-created_at']

    def __str__(self):
        campaign_name = self.campaign.name if self.campaign else 'No Campaign'
        return f"{self.type} - {campaign_name} ({self.created_at})"