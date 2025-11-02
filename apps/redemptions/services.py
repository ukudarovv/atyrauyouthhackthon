from django.db import transaction
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.utils import timezone
from apps.coupons.models import Coupon, CouponStatus
from .models import Redemption
from apps.campaigns.models import TrackEvent, TrackEventType
from apps.referrals.services import grant_referral_if_applicable, get_or_create_customer
from apps.referrals.models import CustomerSource

def rate_limited(user_id: int, scope: str, limit: int = 10, window_sec: int = 60) -> bool:
    """
    Простой rate-limiting на основе кэша
    Возвращает True если лимит превышен
    """
    key = f"rl:{scope}:{user_id}"
    val = cache.get(key, 0)
    if val >= limit:
        return True
    cache.set(key, val + 1, timeout=window_sec)
    return False

@transaction.atomic
def redeem_coupon(*, coupon: Coupon, cashier, amount=None, pos_ref='', note='') -> Redemption:
    """
    Атомарное погашение купона с проверками
    """
    # Проверка статуса купона
    if coupon.status == CouponStatus.REDEEMED:
        raise ValidationError('Купон уже погашен')
    
    if not coupon.is_active():
        if coupon.is_expired():
            raise ValidationError('Срок действия купона истек')
        elif coupon.status == CouponStatus.EXPIRED:
            raise ValidationError('Купон недействителен')
        else:
            raise ValidationError('Купон не может быть использован')

    # Проверка кампании
    if not coupon.campaign.is_running_now():
        raise ValidationError('Кампания неактивна или завершена')

    # Обновляем статус купона
    coupon.status = CouponStatus.REDEEMED
    coupon.uses_count = coupon.uses_count + 1
    coupon.save(update_fields=['status', 'uses_count'])

    # Создаем запись о погашении
    redemption = Redemption.objects.create(
        coupon=coupon,
        cashier=cashier,
        amount=amount,
        pos_ref=pos_ref,
        note=note
    )

    # NEW: если у купона есть телефон, находим/создаём Customer
    if coupon.phone:
        referee = get_or_create_customer(
            business=coupon.campaign.business,
            phone=coupon.phone,
            source=CustomerSource.LANDING
        )
        # Переводим реферальную награду в GRANTED (если есть связывание)
        grant_referral_if_applicable(business=coupon.campaign.business, referee_customer=referee)

    # NEW: создаем приглашение на отзыв после погашения
    try:
        from apps.reviews.services import create_invite
        from apps.reviews.models import ReviewInviteSource
        create_invite(
            business=coupon.campaign.business,
            campaign=coupon.campaign,
            phone=coupon.phone or '',
            source=ReviewInviteSource.REDEMPTION,
            ttl_hours=72,  # 3 дня на оставление отзыва
        )
    except ImportError:
        pass  # Модуль reviews может быть не установлен

    # Записываем событие аналитики
    TrackEvent.objects.create(
        business=coupon.campaign.business,
        campaign=coupon.campaign,
        type=TrackEventType.COUPON_REDEEM,
        utm={},  # внутренняя операция, UTM не актуальны
        ip=None,
        ua='POS System',
        referer=''
    )

    return redemption

def has_business_access(user, business) -> bool:
    """Проверяет доступ пользователя к бизнесу"""
    if user.is_superuser:
        return True
    return business.owner_id == user.id
