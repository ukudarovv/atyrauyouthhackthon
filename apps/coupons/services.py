from django.db import transaction
from django.utils import timezone
from .models import Coupon, CouponStatus

def can_issue_for_phone(campaign, phone: str) -> bool:
    """Проверяет можно ли выдать купон для данного номера телефона"""
    per_phone = campaign.per_phone_limit or 1
    count = Coupon.objects.filter(campaign=campaign, phone=phone).count()
    return count < per_phone

def can_issue_for_campaign(campaign) -> bool:
    """Проверяет можно ли выдать купон для кампании (не превышен ли общий лимит)"""
    return campaign.remaining() > 0

@transaction.atomic
def issue_coupon(campaign, phone: str, expires_at=None) -> Coupon:
    """Выдает новый купон с уникальным кодом"""
    # Проверяем лимиты
    if not can_issue_for_campaign(campaign):
        raise ValueError("Превышен лимит выдачи купонов для кампании")
    
    if not can_issue_for_phone(campaign, phone):
        raise ValueError("Превышен лимит выдачи купонов для данного номера")
    
    # Генерируем уникальный код
    max_attempts = 100
    for attempt in range(max_attempts):
        code = Coupon.generate_code()
        if not Coupon.objects.filter(code=code).exists():
            break
    else:
        raise ValueError("Не удалось сгенерировать уникальный код")

    # Создаем купон
    coupon = Coupon.objects.create(
        campaign=campaign,
        code=code,
        phone=phone,
        expires_at=expires_at,
        status=CouponStatus.ACTIVE,
    )
    return coupon

def get_phone_coupons_count(campaign, phone: str) -> int:
    """Возвращает количество купонов для телефона в данной кампании"""
    return Coupon.objects.filter(campaign=campaign, phone=phone).count()
