from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.businesses.models import Business
from apps.campaigns.models import Campaign

User = settings.AUTH_USER_MODEL

class Review(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='reviews')
    campaign = models.ForeignKey(Campaign, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviews')
    rating = models.PositiveSmallIntegerField(choices=[(i, str(i)) for i in range(1,6)])
    text = models.TextField(blank=True)
    publish_consent = models.BooleanField(default=True)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    phone = models.CharField(max_length=32, blank=True)   # связываем если знаем
    email = models.EmailField(blank=True)
    
    # AI-анализ полей
    ai_sentiment = models.SmallIntegerField(null=True, blank=True, help_text="Тональность от -100 до +100")
    ai_labels = models.JSONField(default=list, blank=True, help_text="Темы отзыва: сервис, вкус, цена и т.д.")
    ai_toxic = models.BooleanField(default=False, help_text="Содержит токсичный/неприемлемый контент")
    ai_summary = models.CharField(max_length=280, blank=True, help_text="Краткое резюме отзыва")

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['business','created_at'])]

    def __str__(self):
        return f"{self.business.name}: {self.rating}★"

class ReviewInviteSource(models.TextChoices):
    MANUAL = 'manual', 'Manual'
    REDEMPTION = 'redemption', 'Redemption'
    ISSUE = 'issue', 'Issue'

class ReviewInvite(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='review_invites')
    campaign = models.ForeignKey(Campaign, on_delete=models.SET_NULL, null=True, blank=True)
    token = models.CharField(max_length=24, unique=True, db_index=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    source = models.CharField(max_length=16, choices=ReviewInviteSource.choices, default=ReviewInviteSource.MANUAL)
    expires_at = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['business','created_at'])]

    def __str__(self):
        return f"Review invite {self.token} ({self.business.name})"

    def is_valid(self):
        if self.used_at:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True