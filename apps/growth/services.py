"""
Сервисы для Growth Hacking механик
"""

from typing import Tuple, Optional, Dict, Any
from django.utils import timezone
from django.db import transaction
from datetime import datetime, timedelta
import logging

from .models import MysteryDrop, MysteryDropAttempt, PowerHour
from apps.coupons.models import Coupon
from apps.customers.models import Customer
from apps.fraud.services import score_issue, RiskDecision
from apps.wallet.models import WalletPass
# from apps.wallet.services import create_wallet_pass  # Будем использовать напрямую
from apps.blasts.models import Blast, BlastTrigger
from apps.blasts.tasks import start_blast_task, run_sync_fallback

logger = logging.getLogger(__name__)


def normalize_phone(phone: str) -> str:
    """Нормализует номер телефона"""
    # Простая нормализация - удаляем все кроме цифр и добавляем +
    digits = ''.join(filter(str.isdigit, phone))
    if digits.startswith('8') and len(digits) == 11:
        digits = '7' + digits[1:]  # 8 -> 7
    if not digits.startswith('7'):
        digits = '7' + digits
    return '+' + digits


def attempt_mystery_drop(mystery_drop: MysteryDrop, phone: str, request=None) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Попытка в Mystery Drop
    Возвращает: (success, message, data)
    """
    
    # Нормализуем телефон
    phone_normalized = normalize_phone(phone)
    
    # Проверяем возможность попытки
    can_attempt, reason = mystery_drop.can_attempt(phone_normalized)
    if not can_attempt:
        return False, reason, {}
    
    try:
        with transaction.atomic():
            # Получаем или создаем клиента
            customer, _ = Customer.objects.get_or_create(
                business=mystery_drop.business,
                phone_e164=phone_normalized,
                defaults={'tags': {}}
            )
            
            # Детерминированный выбор приза
            tier = mystery_drop.pick_tier_deterministic(phone_normalized)
            
            if not tier:
                return False, "Нет доступных призов", {}
            
            # Создаем попытку
            attempt = MysteryDropAttempt.objects.create(
                mystery_drop=mystery_drop,
                phone=phone_normalized,
                customer=customer,
                won=True,  # Всегда выигрыш (разные уровни)
                tier=tier,
                ip_address=request.META.get('REMOTE_ADDR') if request else None,
                user_agent=request.META.get('HTTP_USER_AGENT', '') if request else '',
                session_data={}
            )
            
            # Антифрод проверка
            if request:
                risk_score, risk_reasons, risk_decision = score_issue(
                    request,
                    campaign=mystery_drop.campaign,
                    phone=phone_normalized
                )
                
                attempt.risk_score = risk_score
                attempt.risk_flags = risk_reasons
                attempt.save(update_fields=['risk_score', 'risk_flags'])
                
                # Если высокий риск - блокируем
                if risk_decision == RiskDecision.BLOCK:
                    attempt.won = False
                    attempt.save(update_fields=['won'])
                    return False, "Попытка заблокирована системой безопасности", {}
            
            # Создаем купон
            coupon = Coupon.objects.create(
                campaign=mystery_drop.campaign,
                phone=phone_normalized,
                metadata={
                    'mystery_drop_id': mystery_drop.id,
                    'tier_name': tier.name,
                    'tier_discount': tier.discount_percent,
                    'source': 'mystery_drop'
                }
            )
            
            attempt.coupon = coupon
            attempt.save(update_fields=['coupon'])
            
            # Создаем Wallet карту (если включено)
            wallet_pass = None
            if mystery_drop.auto_wallet_creation:
                try:
                    # Создаем Wallet карту напрямую
                    from apps.wallet.views import create_wallet_pass
                    wallet_pass = WalletPass.objects.create(
                        business=mystery_drop.business,
                        customer=customer,
                        coupon=coupon,
                        object_id=f"mystery_{attempt.id}_{coupon.id}",
                        is_active=True
                    )
                    attempt.wallet_pass = wallet_pass
                    attempt.save(update_fields=['wallet_pass'])
                except Exception as e:
                    logger.error(f"Failed to create wallet pass for mystery drop: {e}")
            
            # Обновляем счетчики
            mystery_drop.total_attempts += 1
            mystery_drop.total_wins += 1
            mystery_drop.save(update_fields=['total_attempts', 'total_wins'])
            
            # Отправляем уведомление (если включено)
            if mystery_drop.send_notification:
                try:
                    send_mystery_drop_notification(attempt)
                except Exception as e:
                    logger.error(f"Failed to send mystery drop notification: {e}")
            
            # Возвращаем результат
            result_data = {
                'tier': {
                    'name': tier.name,
                    'discount_percent': tier.discount_percent,
                    'emoji': tier.emoji,
                    'color': tier.color
                },
                'coupon': {
                    'code': coupon.code,
                    'expires_at': coupon.expires_at.isoformat() if coupon.expires_at else None
                },
                'wallet_url': wallet_pass.get_save_url() if wallet_pass else None
            }
            
            return True, f"Поздравляем! Вы выиграли: {tier.name}", result_data
            
    except Exception as e:
        logger.error(f"Error in mystery drop attempt: {e}")
        return False, "Произошла ошибка, попробуйте позже", {}


def send_mystery_drop_notification(attempt: MysteryDropAttempt):
    """Отправляет уведомление о выигрыше в Mystery Drop"""
    
    # Создаем быструю рассылку победителю
    from apps.blasts.models import MessageTemplate, ContactPoint
    from apps.blasts.services import get_or_create_contact_point, send_message_via_provider
    
    try:
        # Создаем контактную точку для SMS
        contact_point = get_or_create_contact_point(
            business=attempt.mystery_drop.business,
            customer=attempt.customer,
            contact_type='sms',
            value=attempt.phone,
            verified=True
        )
        
        # Простое SMS уведомление
        message = f"🎉 Поздравляем! Вы выиграли {attempt.tier.name}! Ваш код: {attempt.coupon.code}"
        
        # Здесь можно использовать провайдеры SMS для отправки
        logger.info(f"Mystery drop notification sent to {attempt.phone}: {message}")
        
    except Exception as e:
        logger.error(f"Failed to send mystery drop notification: {e}")


def start_power_hour(power_hour: PowerHour) -> bool:
    """Запускает Power Hour"""
    
    if not power_hour.can_start():
        return False
    
    try:
        with transaction.atomic():
            # Обновляем статус
            power_hour.status = 'running'
            power_hour.save(update_fields=['status'])
            
            # Обновляем Wallet карты (если включено)
            if power_hour.auto_wallet_update:
                updated_count = update_wallet_cards_for_power_hour(power_hour)
                power_hour.wallet_updated = updated_count
            
            # Запускаем рассылку (если включено)
            if power_hour.send_blast:
                blast_id = create_power_hour_blast(power_hour)
                if blast_id:
                    run_sync_fallback(start_blast_task, blast_id)
                    power_hour.blast_sent = 1
            
            power_hour.save(update_fields=['wallet_updated', 'blast_sent'])
            
            # Планируем завершение через Celery
            from .tasks import complete_power_hour_task
            run_sync_fallback(
                complete_power_hour_task.apply_async,
                args=[power_hour.id],
                eta=power_hour.ends_at
            )
            
            logger.info(f"Started power hour {power_hour.id}")
            return True
            
    except Exception as e:
        logger.error(f"Failed to start power hour {power_hour.id}: {e}")
        power_hour.status = 'scheduled'
        power_hour.save(update_fields=['status'])
        return False


def update_wallet_cards_for_power_hour(power_hour: PowerHour) -> int:
    """Обновляет Wallet карты для Power Hour"""
    
    # Получаем все активные Wallet карты для кампании
    wallet_passes = WalletPass.objects.filter(
        coupon__campaign=power_hour.campaign,
        coupon__status='active',
        is_active=True
    )
    
    updated_count = 0
    
    for wallet_pass in wallet_passes:
        try:
            # Обновляем данные карты
            update_data = {
                'textModulesData': [
                    {
                        'header': '⚡ POWER HOUR АКТИВЕН!',
                        'body': power_hour.discount_text,
                        'id': 'power_hour'
                    }
                ],
                'hexBackgroundColor': power_hour.wallet_background_color.replace('#', ''),
                'state': 'active'
            }
            
            # Используем Google Wallet API для обновления
            from apps.wallet.gw_client import update_wallet_object
            success = update_wallet_object(wallet_pass.object_id, update_data)
            
            if success:
                updated_count += 1
                
        except Exception as e:
            logger.error(f"Failed to update wallet pass {wallet_pass.id}: {e}")
    
    return updated_count


def create_power_hour_blast(power_hour: PowerHour) -> Optional[int]:
    """Создает рассылку для Power Hour"""
    
    try:
        # Создаем рассылку
        blast = Blast.objects.create(
            business=power_hour.business,
            name=f"⚡ {power_hour.title}",
            description=f"Power Hour для {power_hour.campaign.name}",
            trigger=BlastTrigger.MANUAL,
            segment=power_hour.blast_segment,
            strategy={
                'cascade': [
                    {'channel': 'whatsapp', 'timeout_min': 15},
                    {'channel': 'sms', 'timeout_min': 0}
                ],
                'stop_on': ['delivered_and_clicked'],
                'quiet_hours': {'start': '23:00', 'end': '08:00', 'timezone': 'Asia/Almaty'},
                'max_cost_per_recipient': 5
            },
            budget_cap=500.0
        )
        
        return blast.id
        
    except Exception as e:
        logger.error(f"Failed to create power hour blast: {e}")
        return None


def complete_power_hour(power_hour: PowerHour) -> bool:
    """Завершает Power Hour"""
    
    try:
        with transaction.atomic():
            # Обновляем статус
            power_hour.status = 'completed'
            
            # Возвращаем Wallet карты в исходное состояние
            if power_hour.auto_wallet_update:
                revert_wallet_cards_for_power_hour(power_hour)
            
            # Обновляем метрики
            power_hour.coupons_issued = Coupon.objects.filter(
                campaign=power_hour.campaign,
                created_at__range=[power_hour.starts_at, power_hour.ends_at]
            ).count()
            
            power_hour.coupons_redeemed = Coupon.objects.filter(
                campaign=power_hour.campaign,
                status='redeemed',
                redeemed_at__range=[power_hour.starts_at, power_hour.ends_at]
            ).count()
            
            power_hour.save()
            
            logger.info(f"Completed power hour {power_hour.id}")
            return True
            
    except Exception as e:
        logger.error(f"Failed to complete power hour {power_hour.id}: {e}")
        return False


def revert_wallet_cards_for_power_hour(power_hour: PowerHour):
    """Возвращает Wallet карты в исходное состояние"""
    
    wallet_passes = WalletPass.objects.filter(
        coupon__campaign=power_hour.campaign,
        is_active=True
    )
    
    for wallet_pass in wallet_passes:
        try:
            # Возвращаем исходные данные
            update_data = {
                'textModulesData': [],  # Убираем Power Hour сообщение
                'hexBackgroundColor': None,  # Возвращаем исходный цвет
                'state': 'active'
            }
            
            from apps.wallet.gw_client import update_wallet_object
            update_wallet_object(wallet_pass.object_id, update_data)
            
        except Exception as e:
            logger.error(f"Failed to revert wallet pass {wallet_pass.id}: {e}")


def update_customer_streak(customer, redeemed_at: datetime) -> Dict[str, int]:
    """Обновляет серию посещений клиента"""
    
    # Получаем последнее погашение
    last_redeem = getattr(customer, 'last_redeem_date', None)
    current_streak = getattr(customer, 'streak_count', 0)
    best_streak = getattr(customer, 'streak_best', 0)
    
    today = redeemed_at.date()
    
    if last_redeem:
        days_diff = (today - last_redeem).days
        
        if days_diff == 1:
            # Продолжение серии
            current_streak += 1
        elif days_diff > 7:
            # Серия прервана (больше недели)
            current_streak = 1
        # Если days_diff == 0 (в тот же день) - серия не меняется
    else:
        # Первое погашение
        current_streak = 1
    
    # Обновляем лучший результат
    if current_streak > best_streak:
        best_streak = current_streak
    
    # Сохраняем в базу
    customer.streak_count = current_streak
    customer.streak_best = best_streak
    customer.last_redeem_date = today
    customer.save(update_fields=['streak_count', 'streak_best', 'last_redeem_date'])
    
    return {
        'current_streak': current_streak,
        'best_streak': best_streak,
        'is_new_record': current_streak == best_streak and current_streak > 1
    }
