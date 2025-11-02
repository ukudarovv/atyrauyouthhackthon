from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal


class MysteryDropTier(models.Model):
    """Уровень приза в Mystery Drop"""
    name = models.CharField(max_length=100)  # "Скидка 10%", "Бесплатный кофе"
    discount_percent = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Процент скидки (1-100)"
    )
    probability = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(0.01), MaxValueValidator(100.0)],
        help_text="Вероятность выпадения в процентах (0.01-100.00)"
    )
    emoji = models.CharField(max_length=10, default="🎁", help_text="Эмодзи для отображения")
    color = models.CharField(max_length=7, default="#FFD700", help_text="Цвет в HEX формате")
    is_active = models.BooleanField(default=True)
    
    # Сортировка по ценности (от меньшего к большему)
    order = models.IntegerField(default=0, help_text="Порядок сортировки")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['order', 'discount_percent']
    
    def __str__(self):
        return f"{self.emoji} {self.name} ({self.probability}%)"


class MysteryDrop(models.Model):
    """Конфигурация Mystery Drop для кампании"""
    business = models.ForeignKey('businesses.Business', on_delete=models.CASCADE, related_name='mystery_drops')
    campaign = models.ForeignKey('campaigns.Campaign', on_delete=models.CASCADE, related_name='mystery_drops')
    
    # Основные настройки
    title = models.CharField(max_length=200, default="🎰 Потряси и получи скидку!")
    subtitle = models.CharField(max_length=300, default="Встряхни телефон или поскреби экран")
    
    # Призовые уровни
    tiers = models.ManyToManyField(MysteryDropTier, related_name='mystery_drops')
    
    # Ограничения
    daily_cap_per_phone = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Максимум попыток на один телефон в день"
    )
    daily_cap_total = models.IntegerField(
        default=1000,
        validators=[MinValueValidator(1)],
        help_text="Максимум выдач в день по всей кампании"
    )
    
    # Временные рамки
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    
    # Настройки интерфейса
    scratch_enabled = models.BooleanField(default=True, help_text="Включить скретч-интерфейс")
    shake_enabled = models.BooleanField(default=True, help_text="Включить shake-to-reveal")
    background_color = models.CharField(max_length=7, default="#1a1a1a")
    
    # Интеграции
    auto_wallet_creation = models.BooleanField(default=True, help_text="Автоматически создавать Wallet карты")
    send_notification = models.BooleanField(default=True, help_text="Отправлять уведомление о выигрыше")
    
    # Статус
    enabled = models.BooleanField(default=True)
    
    # Метрики (обновляются автоматически)
    total_attempts = models.IntegerField(default=0)
    total_wins = models.IntegerField(default=0)
    total_redeems = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['business', 'campaign']
        indexes = [
            models.Index(fields=['business', 'enabled']),
            models.Index(fields=['starts_at', 'ends_at']),
        ]
    
    def __str__(self):
        return f"Mystery Drop: {self.campaign.name}"
    
    def is_active(self):
        """Проверяет активность Mystery Drop"""
        now = timezone.now()
        if not self.enabled:
            return False
        if now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True
    
    def get_daily_stats(self, date=None):
        """Возвращает статистику за день"""
        if date is None:
            date = timezone.now().date()
        
        attempts = MysteryDropAttempt.objects.filter(
            mystery_drop=self,
            created_at__date=date
        )
        
        return {
            'attempts': attempts.count(),
            'wins': attempts.filter(won=True).count(),
            'unique_phones': attempts.values('phone').distinct().count(),
            'redeems': attempts.filter(coupon__status='redeemed').count()
        }
    
    def can_attempt(self, phone):
        """Проверяет можно ли делать попытку"""
        if not self.is_active():
            return False, "Mystery Drop неактивен"
        
        today = timezone.now().date()
        
        # Проверяем дневной лимит по телефону
        phone_attempts_today = MysteryDropAttempt.objects.filter(
            mystery_drop=self,
            phone=phone,
            created_at__date=today
        ).count()
        
        if phone_attempts_today >= self.daily_cap_per_phone:
            return False, f"Максимум {self.daily_cap_per_phone} попыток в день"
        
        # Проверяем общий дневной лимит
        total_attempts_today = MysteryDropAttempt.objects.filter(
            mystery_drop=self,
            created_at__date=today
        ).count()
        
        if total_attempts_today >= self.daily_cap_total:
            return False, "Дневной лимит исчерпан, попробуйте завтра"
        
        return True, "OK"
    
    def pick_tier_deterministic(self, phone, date=None):
        """Детерминированный выбор приза по телефону и дате"""
        if date is None:
            date = timezone.now().date()
        
        # Создаем детерминированный seed из телефона + даты + campaign_id
        seed_string = f"{phone}:{date}:{self.campaign_id}"
        seed_hash = hashlib.md5(seed_string.encode()).hexdigest()
        
        # Преобразуем первые 8 символов хеша в число 0-99.99
        hex_value = int(seed_hash[:8], 16)
        random_percent = (hex_value % 10000) / 100.0  # 0.00 - 99.99
        
        # Получаем активные уровни призов, отсортированные по вероятности
        active_tiers = self.tiers.filter(is_active=True).order_by('probability')
        
        if not active_tiers.exists():
            return None
        
        # Находим подходящий уровень
        cumulative_probability = Decimal('0.0')
        
        for tier in active_tiers:
            cumulative_probability += tier.probability
            if Decimal(str(random_percent)) <= cumulative_probability:
                return tier
        
        # Если не попали ни в один уровень, возвращаем последний (самый частый)
        return active_tiers.last()


class MysteryDropAttempt(models.Model):
    """Попытка в Mystery Drop"""
    mystery_drop = models.ForeignKey(MysteryDrop, on_delete=models.CASCADE, related_name='attempts')
    
    # Клиент
    phone = models.CharField(max_length=20)
    customer = models.ForeignKey(
        'customers.Customer', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='mystery_attempts'
    )
    
    # Результат
    won = models.BooleanField(default=False)
    tier = models.ForeignKey(
        MysteryDropTier, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='attempts'
    )
    
    # Выданный купон
    coupon = models.ForeignKey(
        'coupons.Coupon',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mystery_attempts'
    )
    
    # Wallet карта
    wallet_pass = models.ForeignKey(
        'wallet.WalletPass',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mystery_attempts'
    )
    
    # Мета-данные
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    session_data = models.JSONField(default=dict, blank=True)
    
    # Антифрод
    risk_score = models.IntegerField(default=0)
    risk_flags = models.JSONField(default=list, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['mystery_drop', 'phone', 'created_at']),
            models.Index(fields=['mystery_drop', 'created_at']),
            models.Index(fields=['phone', 'created_at']),
        ]
    
    def __str__(self):
        status = "🎉 Выиграл" if self.won else "😔 Не выиграл"
        tier_name = f" ({self.tier.name})" if self.tier else ""
        return f"{self.phone} - {status}{tier_name}"


class PowerHour(models.Model):
    """Конфигурация Power-Hour для кампании"""
    business = models.ForeignKey('businesses.Business', on_delete=models.CASCADE, related_name='power_hours')
    campaign = models.ForeignKey('campaigns.Campaign', on_delete=models.CASCADE, related_name='power_hours')
    
    # Основные настройки
    title = models.CharField(max_length=200, default="⚡ Power Hour!")
    discount_text = models.CharField(max_length=100, default="Скидка 30% следующий час!")
    
    # Временные рамки
    duration_minutes = models.IntegerField(
        default=60,
        validators=[MinValueValidator(15), MaxValueValidator(180)],
        help_text="Длительность в минутах (15-180)"
    )
    
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()  # Вычисляется автоматически
    
    # Wallet настройки
    auto_wallet_update = models.BooleanField(default=True, help_text="Обновлять Wallet карты")
    wallet_background_color = models.CharField(max_length=7, default="#FF4444")
    wallet_text_color = models.CharField(max_length=7, default="#FFFFFF")
    
    # Рассылка
    send_blast = models.BooleanField(default=True, help_text="Отправить каскадную рассылку")
    blast_segment = models.ForeignKey(
        'segments.Segment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Сегмент для рассылки (если пустой - всем)"
    )
    
    # Статус
    STATUS_CHOICES = [
        ('scheduled', 'Запланирован'),
        ('running', 'Активен'),
        ('completed', 'Завершен'),
        ('cancelled', 'Отменен'),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='scheduled')
    
    # Метрики
    blast_sent = models.IntegerField(default=0)
    wallet_updated = models.IntegerField(default=0)
    coupons_issued = models.IntegerField(default=0)
    coupons_redeemed = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-starts_at']
        indexes = [
            models.Index(fields=['business', 'status']),
            models.Index(fields=['starts_at', 'ends_at']),
        ]
    
    def __str__(self):
        return f"Power Hour: {self.campaign.name} ({self.starts_at.strftime('%d.%m %H:%M')})"
    
    def save(self, *args, **kwargs):
        # Автоматически вычисляем ends_at
        if self.starts_at:
            self.ends_at = self.starts_at + timedelta(minutes=self.duration_minutes)
        super().save(*args, **kwargs)
    
    def is_active(self):
        """Проверяет активность Power Hour"""
        now = timezone.now()
        return self.status == 'running' and self.starts_at <= now <= self.ends_at
    
    def can_start(self):
        """Проверяет можно ли запустить"""
        return self.status == 'scheduled' and timezone.now() >= self.starts_at


# Streak модели будут добавлены к существующим Customer и WalletPass
# Добавим поля через миграции:
# Customer.streak_count, Customer.streak_best, Customer.last_redeem_date
# WalletPass.streak_data (JSONField)
