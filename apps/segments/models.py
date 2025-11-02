from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from apps.businesses.models import Business
from apps.customers.models import Customer


class SegmentKind(models.TextChoices):
    SYSTEM = 'system', 'System'
    CUSTOM = 'custom', 'Custom'


class Segment(models.Model):
    """
    Сегмент клиентов с правилами фильтрации
    """
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='segments')
    name = models.CharField(max_length=120, help_text="Название сегмента")
    slug = models.SlugField(max_length=140, blank=True, help_text="URL-friendly имя")
    
    kind = models.CharField(
        max_length=12, 
        choices=SegmentKind.choices, 
        default=SegmentKind.CUSTOM,
        help_text="Тип сегмента: системный или пользовательский"
    )
    
    definition = models.JSONField(
        default=dict, 
        blank=True, 
        help_text="JSON правила фильтрации"
    )
    
    is_dynamic = models.BooleanField(
        default=True, 
        help_text="Динамический сегмент пересчитывается автоматически"
    )
    
    size_cached = models.PositiveIntegerField(
        default=0, 
        help_text="Кэшированный размер сегмента"
    )
    
    preview = models.JSONField(
        default=list, 
        blank=True, 
        help_text="Превью участников (маскированные телефоны)"
    )
    
    last_built_at = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text="Время последнего перестроения"
    )
    
    enabled = models.BooleanField(
        default=True, 
        help_text="Сегмент активен"
    )
    
    # Метаданные для рекомендаций
    description = models.TextField(
        blank=True, 
        help_text="Описание сегмента"
    )
    
    color = models.CharField(
        max_length=7, 
        default='#3B82F6', 
        help_text="Цвет сегмента в HEX"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('business', 'slug')
        indexes = [
            models.Index(fields=['business', 'enabled']),
            models.Index(fields=['business', 'kind']),
            models.Index(fields=['business', 'last_built_at']),
        ]
        ordering = ['kind', 'name']

    def __str__(self):
        return f"{self.business.name}: {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def is_stale(self):
        """Проверяет, устарел ли сегмент (более 24 часов)"""
        if not self.last_built_at:
            return True
        
        from datetime import timedelta
        threshold = timezone.now() - timedelta(hours=24)
        return self.last_built_at < threshold

    @property
    def kind_display(self):
        """Отображение типа сегмента"""
        return "🤖 Системный" if self.kind == SegmentKind.SYSTEM else "👤 Пользовательский"


class SegmentMember(models.Model):
    """
    Участник сегмента
    """
    segment = models.ForeignKey(Segment, on_delete=models.CASCADE, related_name='members')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='segments')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('segment', 'customer')
        indexes = [
            models.Index(fields=['segment', 'customer']),
            models.Index(fields=['customer', 'added_at']),
        ]

    def __str__(self):
        return f"{self.segment.name}: {self.customer.phone_e164}"


# Предопределенные системные сегменты
SYSTEM_SEGMENTS = {
    'new': {
        'name': '🆕 Новые клиенты',
        'description': 'Клиенты, зарегистрировавшиеся за последние 7 дней',
        'color': '#10B981',
        'definition': {
            'logic': 'all',
            'conds': [
                {'field': 'first_seen_days_ago', 'op': '<=', 'value': 7}
            ]
        }
    },
    'active': {
        'name': '🔥 Активные клиенты',
        'description': 'Клиенты с активностью за последние 14 дней и 2+ погашениями',
        'color': '#F59E0B',
        'definition': {
            'logic': 'all',
            'conds': [
                {'field': 'recency_days', 'op': '<=', 'value': 14},
                {'field': 'redeems_count', 'op': '>=', 'value': 2}
            ]
        }
    },
    'vip': {
        'name': '👑 VIP клиенты',
        'description': 'Клиенты с высокими RFM показателями',
        'color': '#8B5CF6',
        'definition': {
            'logic': 'all',
            'conds': [
                {'field': 'r_score', 'op': '>=', 'value': 4},
                {'field': 'f_score', 'op': '>=', 'value': 4},
                {'field': 'm_score', 'op': '>=', 'value': 4}
            ]
        }
    },
    'churn_risk': {
        'name': '⚠️ Риск оттока',
        'description': 'Клиенты без активности 45+ дней, но с историей покупок',
        'color': '#EF4444',
        'definition': {
            'logic': 'all',
            'conds': [
                {'field': 'recency_days', 'op': '>=', 'value': 45},
                {'field': 'redeems_count', 'op': '>=', 'value': 1}
            ]
        }
    },
    'dormant': {
        'name': '😴 Спящие клиенты',
        'description': 'Клиенты без активности более 90 дней',
        'color': '#6B7280',
        'definition': {
            'logic': 'all',
            'conds': [
                {'field': 'recency_days', 'op': '>=', 'value': 90}
            ]
        }
    }
}
