"""
Сервисы для работы с Wallet картами
"""

from typing import Optional
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from .models import WalletPass, WalletClass, WalletPassKind, WalletPassStatus
from .gw_client import (
    ensure_offer_class, 
    build_offer_object, 
    create_save_link,
    update_offer_object,
    send_expiry_notification,
    GoogleWalletError
)


def create_wallet_pass_for_coupon(coupon, platform: str = 'google') -> Optional[WalletPass]:
    """
    Создает Wallet карту для купона
    
    Args:
        coupon: Объект купона
        platform: Платформа (google/apple)
        
    Returns:
        Созданный объект WalletPass или None при ошибке
    """
    if platform != 'google':
        raise NotImplementedError("Only Google Wallet is implemented")
    
    business = coupon.campaign.business
    campaign = coupon.campaign
    
    try:
        # Создаем или получаем класс для бизнеса
        class_data = ensure_offer_class(business)
        class_id = class_data['id']
        
        # Создаем или обновляем запись о классе в БД
        wallet_class, created = WalletClass.objects.get_or_create(
            business=business,
            platform=platform,
            defaults={
                'class_id': class_id,
                'name': f"Скидочные карты {business.name}",
                'background_color': getattr(business, 'brand_color', '#111827'),
                'review_status': class_data.get('reviewStatus', 'UNDER_REVIEW')
            }
        )
        
        # Генерируем уникальный ID объекта
        object_id = f"{settings.GOOGLE_WALLET_ISSUER_ID}.coupon_{coupon.id}_{int(timezone.now().timestamp())}"
        
        # Создаем запись о карте
        wallet_pass = WalletPass.objects.create(
            business=business,
            coupon=coupon,
            campaign=campaign,
            customer_phone=coupon.phone,
            platform=platform,
            class_id=class_id,
            object_id=object_id,
            title=f"Скидка {campaign.name}",
            subtitle="Покажите при оплате",
            barcode_value=coupon.code,
            status=WalletPassStatus.ACTIVE,
            valid_from=timezone.now(),
            valid_until=coupon.expires_at,
        )
        
        return wallet_pass
        
    except GoogleWalletError as e:
        print(f"Failed to create wallet pass: {e}")
        return None


def generate_save_link(wallet_pass: WalletPass) -> Optional[str]:
    """
    Генерирует ссылку "Save to Google Wallet" для карты
    
    Args:
        wallet_pass: Объект WalletPass
        
    Returns:
        URL для сохранения в Wallet или None при ошибке
    """
    try:
        # Строим объект предложения
        offer_object = build_offer_object(wallet_pass)
        
        # Создаем JWT ссылку
        save_link = create_save_link(offer_object)
        
        # Сохраняем ссылку в метаданных
        wallet_pass.metadata['save_link'] = save_link
        wallet_pass.metadata['last_link_generated'] = timezone.now().isoformat()
        wallet_pass.save(update_fields=['metadata'])
        
        return save_link
        
    except GoogleWalletError as e:
        print(f"Failed to generate save link: {e}")
        return None


def update_wallet_pass_content(wallet_pass: WalletPass, updates: dict) -> bool:
    """
    Обновляет содержимое карты в Google Wallet
    
    Args:
        wallet_pass: Объект WalletPass
        updates: Словарь с обновлениями
        
    Returns:
        True если обновление прошло успешно
    """
    try:
        # Обновляем объект в Google Wallet
        update_offer_object(wallet_pass.object_id, updates)
        
        # Обновляем локальную запись
        if 'title' in updates:
            wallet_pass.title = updates['title']
        if 'subtitle' in updates:
            wallet_pass.subtitle = updates['subtitle']
        
        wallet_pass.updated_at = timezone.now()
        wallet_pass.save()
        
        return True
        
    except GoogleWalletError as e:
        print(f"Failed to update wallet pass: {e}")
        return False


def send_expiry_reminder(wallet_pass: WalletPass, hours_before: int = 24) -> bool:
    """
    Отправляет напоминание об истечении срока действия
    
    Args:
        wallet_pass: Объект WalletPass
        hours_before: За сколько часов до истечения отправить
        
    Returns:
        True если напоминание отправлено успешно
    """
    if not wallet_pass.valid_until:
        return False
    
    time_left = wallet_pass.valid_until - timezone.now()
    
    if time_left.total_seconds() <= hours_before * 3600:
        message = None
        
        if time_left.total_seconds() <= 3600:  # Меньше часа
            message = "⏰ Ваша скидка истекает в течение часа!"
            notification_field = 'notification_sent_1h'
        else:  # 24 часа
            days_left = time_left.days
            if days_left < 1:
                message = "⏰ Ваша скидка истекает сегодня!"
            else:
                message = f"⏰ Ваша скидка истекает через {days_left} дн."
            notification_field = 'notification_sent_24h'
        
        # Проверяем, не отправляли ли уже это уведомление
        if getattr(wallet_pass, notification_field, False):
            return False
        
        # Отправляем уведомление
        if send_expiry_notification(wallet_pass, message):
            # Отмечаем что уведомление отправлено
            setattr(wallet_pass, notification_field, True)
            wallet_pass.save(update_fields=[notification_field])
            return True
    
    return False


def get_wallet_passes_for_business(business, platform: str = 'google'):
    """
    Получает все Wallet карты для бизнеса
    
    Args:
        business: Объект бизнеса
        platform: Платформа
        
    Returns:
        QuerySet с WalletPass объектами
    """
    return WalletPass.objects.filter(
        business=business,
        platform=platform
    ).select_related('coupon', 'campaign').order_by('-created_at')


def get_expiring_passes(hours_ahead: int = 24):
    """
    Получает карты, срок действия которых истекает в ближайшее время
    
    Args:
        hours_ahead: В течение скольких часов искать истекающие карты
        
    Returns:
        QuerySet с истекающими картами
    """
    cutoff_time = timezone.now() + timedelta(hours=hours_ahead)
    
    return WalletPass.objects.filter(
        status=WalletPassStatus.ACTIVE,
        valid_until__lte=cutoff_time,
        valid_until__gte=timezone.now()
    ).select_related('coupon', 'campaign', 'business')


def expire_wallet_pass(wallet_pass: WalletPass):
    """
    Помечает карту как истекшую
    
    Args:
        wallet_pass: Объект WalletPass
    """
    try:
        # Обновляем статус в Google Wallet
        updates = {
            "state": "expired",
            "textModulesData": [
                {
                    "header": "Статус",
                    "body": "Срок действия истек"
                }
            ]
        }
        
        update_offer_object(wallet_pass.object_id, updates)
        
        # Обновляем локальный статус
        wallet_pass.status = WalletPassStatus.EXPIRED
        wallet_pass.save(update_fields=['status'])
        
        return True
        
    except GoogleWalletError as e:
        print(f"Failed to expire wallet pass: {e}")
        return False


def get_wallet_stats_for_business(business):
    """
    Получает статистику по Wallet картам для бизнеса
    
    Args:
        business: Объект бизнеса
        
    Returns:
        Словарь со статистикой
    """
    passes = WalletPass.objects.filter(business=business)
    
    stats = {
        'total_passes': passes.count(),
        'active_passes': passes.filter(status=WalletPassStatus.ACTIVE).count(),
        'expired_passes': passes.filter(status=WalletPassStatus.EXPIRED).count(),
        'passes_by_platform': {},
        'recent_passes': passes.order_by('-created_at')[:5]
    }
    
    # Статистика по платформам
    for platform in WalletPassKind.values:
        count = passes.filter(platform=platform).count()
        if count > 0:
            stats['passes_by_platform'][platform] = count
    
    return stats
