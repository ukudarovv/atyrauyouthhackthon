from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from slugify import slugify

User = settings.AUTH_USER_MODEL

class Business(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_businesses')
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    address = models.CharField(max_length=255, blank=True)
    timezone = models.CharField(max_length=64, default='Asia/Atyrau')
    brand_color = models.CharField(max_length=7, default='#111827')  # #RRGGBB
    contacts = models.JSONField(default=dict, blank=True)
    settings = models.JSONField(default=dict, blank=True)  # настройки бизнеса (включая антифрод)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or 'biz'
            slug = base
            i = 1
            # гарантируем уникальность
            while Business.objects.filter(slug=slug).exists():
                i += 1
                slug = f'{base}-{i}'
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('businesses:list')

class Location(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='locations')
    name = models.CharField(max_length=160)
    address = models.CharField(max_length=255, blank=True)
    geo_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geo_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    opening_hours = models.JSONField(default=dict, blank=True)  # например {"mon": "09:00-18:00", ...}
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.business.name})'