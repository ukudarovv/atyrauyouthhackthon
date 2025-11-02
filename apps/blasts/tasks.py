"""
Celery задачи для омниканальных рассылок
"""

from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_blast_orchestrator(self):
    """
    Периодическая задача для обработки всех активных рассылок
    Запускается каждые 5 минут
    """
    try:
        from .orchestrator import process_all_pending_blasts, process_scheduled_blasts
        
        # Обрабатываем запланированные рассылки
        process_scheduled_blasts()
        
        # Обрабатываем активные рассылки
        process_all_pending_blasts()
        
        logger.info("Blast orchestrator task completed successfully")
        
    except Exception as e:
        logger.error(f"Blast orchestrator task failed: {e}")
        # Повторяем попытку через 2 минуты
        raise self.retry(countdown=120)


@shared_task(bind=True, max_retries=2)
def start_blast_task(self, blast_id: int):
    """Запускает рассылку"""
    try:
        from .models import Blast
        from .orchestrator import BlastOrchestrator
        
        blast = Blast.objects.get(id=blast_id)
        orchestrator = BlastOrchestrator(blast)
        
        success = orchestrator.start_blast()
        
        if success:
            logger.info(f"Successfully started blast {blast_id}")
        else:
            logger.error(f"Failed to start blast {blast_id}")
            
        return success
        
    except Exception as e:
        logger.error(f"Error starting blast {blast_id}: {e}")
        raise self.retry(countdown=60)


@shared_task(bind=True, max_retries=1)
def pause_blast_task(self, blast_id: int):
    """Приостанавливает рассылку"""
    try:
        from .models import Blast
        from .orchestrator import BlastOrchestrator
        
        blast = Blast.objects.get(id=blast_id)
        orchestrator = BlastOrchestrator(blast)
        orchestrator.pause_blast()
        
        logger.info(f"Paused blast {blast_id}")
        
    except Exception as e:
        logger.error(f"Error pausing blast {blast_id}: {e}")


@shared_task(bind=True, max_retries=1)
def resume_blast_task(self, blast_id: int):
    """Возобновляет рассылку"""
    try:
        from .models import Blast
        from .orchestrator import BlastOrchestrator
        
        blast = Blast.objects.get(id=blast_id)
        orchestrator = BlastOrchestrator(blast)
        orchestrator.resume_blast()
        
        logger.info(f"Resumed blast {blast_id}")
        
    except Exception as e:
        logger.error(f"Error resuming blast {blast_id}: {e}")


@shared_task(bind=True, max_retries=1)
def cancel_blast_task(self, blast_id: int):
    """Отменяет рассылку"""
    try:
        from .models import Blast
        from .orchestrator import BlastOrchestrator
        
        blast = Blast.objects.get(id=blast_id)
        orchestrator = BlastOrchestrator(blast)
        orchestrator.cancel_blast()
        
        logger.info(f"Cancelled blast {blast_id}")
        
    except Exception as e:
        logger.error(f"Error cancelling blast {blast_id}: {e}")


@shared_task(bind=True, max_retries=2)
def send_single_message_task(self, delivery_attempt_id: int):
    """Отправляет одно сообщение"""
    try:
        from .models import DeliveryAttempt
        from .services import send_message_via_provider
        
        delivery_attempt = DeliveryAttempt.objects.get(id=delivery_attempt_id)
        success = send_message_via_provider(delivery_attempt)
        
        if success:
            logger.info(f"Successfully sent message {delivery_attempt_id}")
        else:
            logger.warning(f"Failed to send message {delivery_attempt_id}")
            
        return success
        
    except Exception as e:
        logger.error(f"Error sending message {delivery_attempt_id}: {e}")
        raise self.retry(countdown=30)


@shared_task(bind=True)
def handle_delivery_webhook_task(self, external_id: str, status: str, metadata: dict = None):
    """Обрабатывает webhook от провайдера"""
    try:
        from .orchestrator import handle_delivery_webhook
        
        handle_delivery_webhook(external_id, status, metadata)
        logger.info(f"Processed webhook for {external_id}: {status}")
        
    except Exception as e:
        logger.error(f"Error processing webhook {external_id}: {e}")


@shared_task(bind=True)
def sync_contact_points_task(self, business_id: int):
    """Синхронизирует контактные точки клиентов"""
    try:
        from apps.businesses.models import Business
        from apps.customers.models import Customer
        from .services import get_or_create_contact_point
        
        business = Business.objects.get(id=business_id)
        customers = Customer.objects.filter(business=business)
        
        created_count = 0
        updated_count = 0
        
        for customer in customers:
            # Создаем контактную точку для телефона (SMS/WhatsApp)
            if customer.phone_e164:
                sms_point, created = get_or_create_contact_point(
                    business=business,
                    customer=customer,
                    contact_type='sms',
                    value=customer.phone_e164,
                    verified=True
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1
                
                # Также создаем для WhatsApp
                wa_point, created = get_or_create_contact_point(
                    business=business,
                    customer=customer,
                    contact_type='whatsapp',
                    value=customer.phone_e164,
                    verified=False  # WhatsApp требует отдельной верификации
                )
                if created:
                    created_count += 1
            
            # Создаем контактную точку для email если есть
            email = customer.tags.get('email')
            if email:
                email_point, created = get_or_create_contact_point(
                    business=business,
                    customer=customer,
                    contact_type='email',
                    value=email,
                    verified=False
                )
                if created:
                    created_count += 1
        
        logger.info(f"Synced contact points for business {business_id}: {created_count} created, {updated_count} updated")
        
        return {'created': created_count, 'updated': updated_count}
        
    except Exception as e:
        logger.error(f"Error syncing contact points for business {business_id}: {e}")


@shared_task(bind=True)
def cleanup_old_delivery_attempts_task(self, days_old: int = 30):
    """Очищает старые попытки доставки"""
    try:
        from .models import DeliveryAttempt
        
        cutoff_date = timezone.now() - timedelta(days=days_old)
        
        deleted_count, _ = DeliveryAttempt.objects.filter(
            created_at__lt=cutoff_date,
            status__in=['failed', 'bounced']
        ).delete()
        
        logger.info(f"Cleaned up {deleted_count} old delivery attempts")
        return deleted_count
        
    except Exception as e:
        logger.error(f"Error cleaning up delivery attempts: {e}")


@shared_task(bind=True)
def cleanup_old_short_link_clicks_task(self, days_old: int = 90):
    """Очищает старые клики по коротким ссылкам"""
    try:
        from .models import ShortLinkClick
        
        cutoff_date = timezone.now() - timedelta(days=days_old)
        
        deleted_count, _ = ShortLinkClick.objects.filter(
            clicked_at__lt=cutoff_date
        ).delete()
        
        logger.info(f"Cleaned up {deleted_count} old short link clicks")
        return deleted_count
        
    except Exception as e:
        logger.error(f"Error cleaning up short link clicks: {e}")


@shared_task(bind=True, max_retries=2)
def send_expiry_reminder_task(self, coupon_id: int, hours_before: int = 24):
    """Отправляет напоминание об истечении купона"""
    try:
        from apps.coupons.models import Coupon
        from apps.customers.models import Customer
        from .models import Blast, BlastTrigger, MessageTemplate
        from .orchestrator import BlastOrchestrator
        
        coupon = Coupon.objects.get(id=coupon_id)
        
        # Находим клиента по телефону
        try:
            customer = Customer.objects.get(
                business=coupon.campaign.business,
                phone_e164=coupon.phone
            )
        except Customer.DoesNotExist:
            logger.warning(f"Customer not found for coupon {coupon_id}")
            return
        
        # Проверяем что купон еще активен
        if not coupon.is_active():
            return
        
        # Создаем рассылку-напоминание
        blast = Blast.objects.create(
            business=coupon.campaign.business,
            name=f"Напоминание об истечении купона {coupon.code}",
            trigger=BlastTrigger.EXPIRY_24H if hours_before >= 24 else BlastTrigger.EXPIRY_1H,
            strategy={
                'cascade': [
                    {'channel': 'whatsapp', 'timeout_min': 0},
                    {'channel': 'sms', 'timeout_min': 0}
                ],
                'max_cost_per_recipient': 10
            }
        )
        
        # Создаем получателя вручную
        from .models import BlastRecipient, BlastRecipientStatus
        from .services import collect_contact_points_for_customer
        
        contact_points_by_type = collect_contact_points_for_customer(blast.business, customer)
        contact_point_ids = []
        
        # Формируем список контактных точек
        for channel in ['whatsapp', 'sms']:
            if channel in contact_points_by_type:
                contact_point_ids.append(contact_points_by_type[channel][0].id)
        
        if contact_point_ids:
            BlastRecipient.objects.create(
                blast=blast,
                customer=customer,
                contact_points=contact_point_ids,
                status=BlastRecipientStatus.PENDING,
                next_attempt_at=timezone.now()
            )
            
            blast.total_recipients = 1
            blast.save()
            
            # Запускаем рассылку
            orchestrator = BlastOrchestrator(blast)
            orchestrator.start_blast()
            
            logger.info(f"Started expiry reminder for coupon {coupon_id}")
        
    except Exception as e:
        logger.error(f"Error sending expiry reminder for coupon {coupon_id}: {e}")
        raise self.retry(countdown=300)


@shared_task(bind=True)
def update_contact_point_activity_task(self, contact_point_id: int):
    """Обновляет время последней активности контактной точки"""
    try:
        from .models import ContactPoint
        
        contact_point = ContactPoint.objects.get(id=contact_point_id)
        contact_point.last_seen_at = timezone.now()
        contact_point.save(update_fields=['last_seen_at'])
        
    except Exception as e:
        logger.error(f"Error updating contact point activity {contact_point_id}: {e}")


# Функция для синхронного выполнения задач (если Celery недоступен)
def run_sync_fallback(task_func, *args, **kwargs):
    """Запускает задачу синхронно если Celery недоступен"""
    try:
        # Пытаемся запустить асинхронно
        return task_func.delay(*args, **kwargs)
    except Exception:
        # Если не получается, запускаем синхронно
        return task_func(*args, **kwargs)
