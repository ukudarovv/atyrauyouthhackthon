"""
Сигналы для Growth Hacking механик
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
import logging

from apps.redemptions.models import Redemption
from .services import update_customer_streak
from .tasks import update_wallet_streak_task, send_streak_milestone_notification_task, run_sync_fallback

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Redemption)
def update_streak_on_redemption(sender, instance: Redemption, created, **kwargs):
    """Обновляет серию посещений при погашении купона"""
    
    if not created:
        return
    
    try:
        # Получаем клиента
        from apps.customers.models import Customer
        
        customer = Customer.objects.filter(
            business=instance.coupon.campaign.business,
            phone_e164=instance.coupon.phone
        ).first()
        
        if not customer:
            logger.warning(f"Customer not found for redemption {instance.id}")
            return
        
        # Обновляем серию
        streak_data = update_customer_streak(customer, instance.redeemed_at)
        
        current_streak = streak_data['current_streak']
        is_new_record = streak_data['is_new_record']
        
        logger.info(f"Updated streak for customer {customer.id}: {current_streak} (record: {is_new_record})")
        
        # Обновляем Wallet карты асинхронно
        run_sync_fallback(update_wallet_streak_task, customer.id, streak_data)
        
        # Отправляем уведомление о важных milestone
        milestone_notifications = [3, 5, 10, 15, 20, 25, 30]
        
        if current_streak in milestone_notifications:
            run_sync_fallback(send_streak_milestone_notification_task, customer.id, current_streak)
        
    except Exception as e:
        logger.error(f"Error updating streak for redemption {instance.id}: {e}")
