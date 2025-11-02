"""
Celery задачи для Growth Hacking
"""

from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2)
def complete_power_hour_task(self, power_hour_id: int):
    """Завершает Power Hour по расписанию"""
    try:
        from .models import PowerHour
        from .services import complete_power_hour
        
        power_hour = PowerHour.objects.get(id=power_hour_id)
        
        if power_hour.status == 'running':
            success = complete_power_hour(power_hour)
            if success:
                logger.info(f"Successfully completed power hour {power_hour_id}")
            else:
                logger.error(f"Failed to complete power hour {power_hour_id}")
        else:
            logger.info(f"Power hour {power_hour_id} is not running, skipping completion")
            
    except Exception as e:
        logger.error(f"Error completing power hour {power_hour_id}: {e}")
        raise self.retry(countdown=60)


@shared_task(bind=True, max_retries=3)
def update_wallet_streak_task(self, customer_id: int, streak_data: dict):
    """Обновляет Wallet карты с информацией о серии"""
    try:
        from apps.customers.models import Customer
        from apps.wallet.models import WalletPass
        from apps.wallet.gw_client import update_wallet_object
        
        customer = Customer.objects.get(id=customer_id)
        current_streak = streak_data['current_streak']
        is_new_record = streak_data['is_new_record']
        
        # Находим активные Wallet карты клиента
        wallet_passes = WalletPass.objects.filter(
            customer=customer,
            is_active=True,
            coupon__status='active'
        )
        
        updated_count = 0
        
        for wallet_pass in wallet_passes:
            try:
                # Формируем сообщение о серии
                if current_streak >= 5:
                    streak_message = f"🔥 Серия: {current_streak} подряд!"
                    streak_emoji = "🔥"
                elif current_streak >= 3:
                    streak_message = f"⭐ Серия: {current_streak} визита"
                    streak_emoji = "⭐"
                else:
                    streak_message = f"📈 Визитов: {current_streak}"
                    streak_emoji = "📈"
                
                # Обновляем данные карты
                update_data = {
                    'textModulesData': [
                        {
                            'header': f'{streak_emoji} ВАША СЕРИЯ',
                            'body': streak_message,
                            'id': 'streak_counter'
                        }
                    ]
                }
                
                # Если новый рекорд - меняем цвет
                if is_new_record and current_streak >= 3:
                    update_data['hexBackgroundColor'] = 'FFD700'  # Золотой цвет
                
                # Отправляем обновление
                from apps.wallet.gw_client import update_wallet_object
                success = update_wallet_object(wallet_pass.object_id, update_data)
                
                if success:
                    # Сохраняем данные серии в карте
                    wallet_pass.streak_data = {
                        'current_streak': current_streak,
                        'updated_at': timezone.now().isoformat(),
                        'is_record': is_new_record
                    }
                    wallet_pass.save(update_fields=['streak_data'])
                    updated_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to update wallet pass {wallet_pass.id} with streak: {e}")
        
        logger.info(f"Updated {updated_count} wallet passes with streak data for customer {customer_id}")
        
    except Exception as e:
        logger.error(f"Error updating wallet streak for customer {customer_id}: {e}")
        raise self.retry(countdown=30)


@shared_task(bind=True)
def cleanup_old_mystery_attempts_task(self, days_old: int = 30):
    """Очищает старые попытки Mystery Drop"""
    try:
        from .models import MysteryDropAttempt
        
        cutoff_date = timezone.now() - timedelta(days=days_old)
        
        # Удаляем только неуспешные попытки
        deleted_count, _ = MysteryDropAttempt.objects.filter(
            created_at__lt=cutoff_date,
            won=False
        ).delete()
        
        logger.info(f"Cleaned up {deleted_count} old mystery drop attempts")
        return deleted_count
        
    except Exception as e:
        logger.error(f"Error cleaning up mystery attempts: {e}")


@shared_task(bind=True)
def process_scheduled_power_hours_task(self):
    """Обрабатывает запланированные Power Hours"""
    try:
        from .models import PowerHour
        from .services import start_power_hour
        
        now = timezone.now()
        
        # Находим Power Hours, которые должны запуститься
        scheduled_power_hours = PowerHour.objects.filter(
            status='scheduled',
            starts_at__lte=now
        )
        
        started_count = 0
        
        for power_hour in scheduled_power_hours:
            try:
                if start_power_hour(power_hour):
                    started_count += 1
                    logger.info(f"Started power hour {power_hour.id}")
                else:
                    logger.warning(f"Failed to start power hour {power_hour.id}")
            except Exception as e:
                logger.error(f"Error starting power hour {power_hour.id}: {e}")
        
        if started_count > 0:
            logger.info(f"Started {started_count} power hours")
        
        return started_count
        
    except Exception as e:
        logger.error(f"Error processing scheduled power hours: {e}")


@shared_task(bind=True)
def send_streak_milestone_notification_task(self, customer_id: int, milestone: int):
    """Отправляет уведомление о достижении важной серии"""
    try:
        from apps.customers.models import Customer
        from apps.blasts.services import get_or_create_contact_point
        
        customer = Customer.objects.get(id=customer_id)
        
        # Создаем контактную точку для уведомления
        contact_point = get_or_create_contact_point(
            business=customer.business,
            customer=customer,
            contact_type='sms',
            value=customer.phone_e164,
            verified=True
        )
        
        # Формируем сообщение в зависимости от milestone
        if milestone == 3:
            message = f"🎉 Поздравляем! Вы посетили нас 3 раза подряд! Вас ждет особый сюрприз при следующем визите!"
        elif milestone == 5:
            message = f"🔥 Невероятно! 5 визитов подряд! Вы настоящий VIP-клиент! Специальная скидка уже в вашей Wallet карте!"
        elif milestone == 10:
            message = f"👑 ЛЕГЕНДА! 10 визитов подряд! Вы попали в наш Зал славы! Ждем вас с эксклюзивным предложением!"
        else:
            message = f"⭐ Отличная серия - {milestone} визитов подряд! Продолжайте в том же духе!"
        
        # Здесь можно использовать провайдеры SMS для отправки
        logger.info(f"Streak milestone notification for customer {customer_id}: {message}")
        
    except Exception as e:
        logger.error(f"Error sending streak milestone notification: {e}")


@shared_task(bind=True)
def update_mystery_drop_stats_task(self, mystery_drop_id: int):
    """Обновляет статистику Mystery Drop"""
    try:
        from .models import MysteryDrop, MysteryDropAttempt
        
        mystery_drop = MysteryDrop.objects.get(id=mystery_drop_id)
        
        # Пересчитываем статистику
        attempts = MysteryDropAttempt.objects.filter(mystery_drop=mystery_drop)
        
        mystery_drop.total_attempts = attempts.count()
        mystery_drop.total_wins = attempts.filter(won=True).count()
        mystery_drop.total_redeems = attempts.filter(coupon__status='redeemed').count()
        
        mystery_drop.save(update_fields=['total_attempts', 'total_wins', 'total_redeems'])
        
        logger.info(f"Updated stats for mystery drop {mystery_drop_id}")
        
    except Exception as e:
        logger.error(f"Error updating mystery drop stats {mystery_drop_id}: {e}")


# Функция для синхронного выполнения задач (если Celery недоступен)
def run_sync_fallback(task_func, *args, **kwargs):
    """Запускает задачу синхронно если Celery недоступен"""
    try:
        # Пытаемся запустить асинхронно
        return task_func.delay(*args, **kwargs)
    except Exception:
        # Если не получается, запускаем синхронно
        return task_func(*args, **kwargs)
