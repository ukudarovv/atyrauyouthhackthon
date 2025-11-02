from django.db import models
from django.utils import timezone
from decimal import Decimal
from apps.businesses.models import Business


class Customer(models.Model):
    """
    Агрегированная модель клиента по телефону
    """
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='analytics_customers')
    phone_e164 = models.CharField(max_length=32, help_text="Нормализованный номер телефона")
    
    # Временные метки
    first_seen = models.DateTimeField(null=True, blank=True, help_text="Первое взаимодействие")
    last_issue_at = models.DateTimeField(null=True, blank=True, help_text="Последняя выдача купона")
    last_redeem_at = models.DateTimeField(null=True, blank=True, help_text="Последнее погашение")

    # Агрегированные метрики
    issues_count = models.PositiveIntegerField(default=0, help_text="Количество выданных купонов")
    redeems_count = models.PositiveIntegerField(default=0, help_text="Количество погашений")
    redeem_amount_total = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Общая сумма погашений"
    )

    # RFM метрики (обновляется ночной задачей)
    recency_days = models.PositiveIntegerField(
        default=9999, 
        help_text="Дни с последнего погашения"
    )
    r_score = models.PositiveSmallIntegerField(
        default=1, 
        help_text="Recency score (1-5)"
    )
    f_score = models.PositiveSmallIntegerField(
        default=1, 
        help_text="Frequency score (1-5)"
    )
    m_score = models.PositiveSmallIntegerField(
        default=1, 
        help_text="Monetary score (1-5)"
    )

    # Дополнительные теги
    tags = models.JSONField(
        default=list, 
        blank=True, 
        help_text="Теги клиента: ['coffee', 'lunch']"
    )
    
    # Streak (серии посещений) для Growth механик
    streak_count = models.IntegerField(default=0, help_text="Текущая серия посещений")
    streak_best = models.IntegerField(default=0, help_text="Лучшая серия посещений")
    last_redeem_date = models.DateField(null=True, blank=True, help_text="Дата последнего погашения")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('business', 'phone_e164')
        indexes = [
            models.Index(fields=['business', 'phone_e164']),
            models.Index(fields=['business', 'recency_days']),
            models.Index(fields=['business', 'redeems_count']),
            models.Index(fields=['business', 'r_score', 'f_score', 'm_score']),
        ]
        ordering = ['-last_redeem_at', '-redeems_count']

    def __str__(self):
        return f"{self.business.name}:{self.phone_e164}"

    @property
    def rfm_segment(self):
        """Возвращает RFM сегмент как строку"""
        return f"R{self.r_score}F{self.f_score}M{self.m_score}"

    @property
    def is_vip(self):
        """VIP клиент (высокие RFM показатели)"""
        return self.r_score >= 4 and self.f_score >= 4 and self.m_score >= 4

    @property
    def is_churn_risk(self):
        """Риск оттока (давно не было активности)"""
        return self.recency_days >= 45 and self.redeems_count >= 1

    @property
    def is_new(self):
        """Новый клиент (недавно зарегистрировался)"""
        if not self.first_seen:
            return False
        days_since_first = (timezone.now() - self.first_seen).days
        return days_since_first <= 7

    @property
    def lifetime_value(self):
        """Примерная оценка LTV"""
        return float(self.redeem_amount_total)
