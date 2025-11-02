"""
Оркестратор каскадных рассылок
Управляет процессом отправки сообщений по каскаду каналов
"""

from typing import List, Dict, Any, Optional
from django.utils import timezone
from django.db.models import Q, F
from datetime import timedelta
import logging

from .models import (
    Blast, BlastStatus, BlastRecipient, BlastRecipientStatus,
    DeliveryAttempt, DeliveryStatus, ContactPoint, MessageTemplate
)
from .services import (
    create_blast_recipients, send_message_via_provider,
    get_message_preferences, check_quiet_hours, check_frequency_limits
)

logger = logging.getLogger(__name__)


class BlastOrchestrator:
    """Основной оркестратор рассылок"""
    
    def __init__(self, blast: Blast):
        self.blast = blast
        self.strategy = blast.strategy or self._get_default_strategy()
    
    def _get_default_strategy(self) -> Dict[str, Any]:
        """Возвращает стратегию по умолчанию"""
        return {
            'cascade': [
                {'channel': 'whatsapp', 'timeout_min': 60},
                {'channel': 'sms', 'timeout_min': 180},
                {'channel': 'email', 'timeout_min': 0}
            ],
            'stop_on': ['delivered_and_clicked', 'redeemed'],
            'quiet_hours': {'start': '21:00', 'end': '09:00', 'timezone': 'Asia/Almaty'},
            'max_cost_per_recipient': 120,
            'max_attempts_per_step': 3
        }
    
    def start_blast(self) -> bool:
        """Запускает рассылку"""
        if not self.blast.can_start():
            logger.warning(f"Cannot start blast {self.blast.id} in status {self.blast.status}")
            return False
        
        try:
            # Создаем получателей
            recipients_count = create_blast_recipients(self.blast)
            
            if recipients_count == 0:
                self.blast.status = BlastStatus.COMPLETED
                self.blast.completed_at = timezone.now()
                self.blast.save()
                logger.info(f"Blast {self.blast.id} completed immediately - no recipients")
                return True
            
            # Обновляем статус рассылки
            self.blast.status = BlastStatus.RUNNING
            self.blast.started_at = timezone.now()
            self.blast.save()
            
            # Запускаем первый шаг для всех получателей
            self._schedule_next_attempts()
            
            logger.info(f"Started blast {self.blast.id} with {recipients_count} recipients")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start blast {self.blast.id}: {e}")
            self.blast.status = BlastStatus.CANCELLED
            self.blast.save()
            return False
    
    def _schedule_next_attempts(self):
        """Планирует следующие попытки отправки"""
        # Получаем получателей, которые готовы к следующей попытке
        ready_recipients = BlastRecipient.objects.filter(
            blast=self.blast,
            status=BlastRecipientStatus.PENDING,
            next_attempt_at__lte=timezone.now()
        )
        
        for recipient in ready_recipients:
            self._process_recipient(recipient)
    
    def _process_recipient(self, recipient: BlastRecipient):
        """Обрабатывает получателя рассылки"""
        try:
            # Проверяем превышение бюджета
            if self._is_budget_exceeded(recipient):
                recipient.status = BlastRecipientStatus.SKIPPED
                recipient.save()
                return
            
            # Проверяем условия остановки
            if self._should_stop_for_recipient(recipient):
                recipient.status = BlastRecipientStatus.COMPLETED
                recipient.save()
                return
            
            # Получаем текущий шаг каскада
            cascade = self.strategy.get('cascade', [])
            
            if recipient.current_step >= len(cascade):
                # Прошли все шаги каскада
                recipient.status = BlastRecipientStatus.COMPLETED
                recipient.save()
                return
            
            step = cascade[recipient.current_step]
            channel = step['channel']
            
            # Находим контактную точку для этого канала
            contact_point = self._find_contact_point(recipient, channel)
            
            if not contact_point:
                # Нет подходящей контактной точки, переходим к следующему шагу
                self._advance_to_next_step(recipient, step)
                return
            
            # Проверяем ограничения
            if not self._can_send_to_recipient(recipient, contact_point, channel):
                # Откладываем отправку
                self._schedule_retry(recipient, step)
                return
            
            # Создаем попытку доставки
            delivery_attempt = self._create_delivery_attempt(recipient, contact_point, channel, step)
            
            # Отправляем сообщение
            success = send_message_via_provider(delivery_attempt)
            
            # Обновляем статистику рассылки
            self._update_blast_stats(success)
            
            if success:
                # Планируем проверку результата через timeout
                timeout_min = step.get('timeout_min', 0)
                if timeout_min > 0:
                    recipient.next_attempt_at = timezone.now() + timedelta(minutes=timeout_min)
                    recipient.status = BlastRecipientStatus.PROCESSING
                else:
                    # Если timeout = 0, считаем что все готово
                    recipient.status = BlastRecipientStatus.COMPLETED
                
                recipient.attempts_count += 1
                recipient.save()
            else:
                # Неудачная отправка, пробуем повторить или переходим дальше
                self._handle_failed_attempt(recipient, step)
                
        except Exception as e:
            logger.error(f"Error processing recipient {recipient.id}: {e}")
            recipient.status = BlastRecipientStatus.FAILED
            recipient.save()
    
    def _find_contact_point(self, recipient: BlastRecipient, channel: str) -> Optional[ContactPoint]:
        """Находит подходящую контактную точку для канала"""
        contact_point_ids = recipient.contact_points
        
        for cp_id in contact_point_ids:
            try:
                contact_point = ContactPoint.objects.get(id=cp_id, type=channel, opt_in=True)
                return contact_point
            except ContactPoint.DoesNotExist:
                continue
        
        return None
    
    def _can_send_to_recipient(self, recipient: BlastRecipient, contact_point: ContactPoint, channel: str) -> bool:
        """Проверяет можно ли отправить сообщение получателю"""
        customer = recipient.customer
        business = self.blast.business
        
        # Проверяем тихие часы
        preferences = get_message_preferences(business, customer)
        if check_quiet_hours(preferences):
            return False
        
        # Проверяем лимиты частоты
        if not check_frequency_limits(business, customer, channel):
            return False
        
        # Проверяем что контакт не в blacklist
        if not contact_point.opt_in or not contact_point.verified:
            return False
        
        return True
    
    def _create_delivery_attempt(self, recipient: BlastRecipient, contact_point: ContactPoint, channel: str, step: Dict) -> DeliveryAttempt:
        """Создает попытку доставки"""
        # Находим подходящий шаблон
        template = self._find_template(channel, recipient.customer)
        
        # Определяем тему и тело сообщения
        if template:
            subject = template.subject
            body = template.body_text
        else:
            # Базовое сообщение если нет шаблона
            subject = f"Сообщение от {self.blast.business.name}"
            body = f"Уважаемый клиент, у нас есть предложение для вас! {self.blast.name}"
        
        return DeliveryAttempt.objects.create(
            blast_recipient=recipient,
            contact_point=contact_point,
            channel=channel,
            provider=step.get('provider', 'dummy'),
            template=template,
            subject=subject,
            body=body,
            status=DeliveryStatus.QUEUED
        )
    
    def _find_template(self, channel: str, customer) -> Optional[MessageTemplate]:
        """Находит подходящий шаблон для канала"""
        preferences = get_message_preferences(self.blast.business, customer)
        
        return MessageTemplate.objects.filter(
            business=self.blast.business,
            channel=channel,
            locale=preferences.locale,
            is_active=True
        ).first()
    
    def _advance_to_next_step(self, recipient: BlastRecipient, current_step: Dict):
        """Переходит к следующему шагу каскада"""
        recipient.current_step += 1
        recipient.next_attempt_at = timezone.now()
        recipient.save()
    
    def _schedule_retry(self, recipient: BlastRecipient, step: Dict):
        """Планирует повторную попытку"""
        retry_delay = step.get('retry_delay_min', 30)
        recipient.next_attempt_at = timezone.now() + timedelta(minutes=retry_delay)
        recipient.save()
    
    def _handle_failed_attempt(self, recipient: BlastRecipient, step: Dict):
        """Обрабатывает неудачную попытку"""
        max_attempts = self.strategy.get('max_attempts_per_step', 3)
        
        if recipient.attempts_count >= max_attempts:
            # Превышено максимальное количество попыток, переходим к следующему шагу
            self._advance_to_next_step(recipient, step)
        else:
            # Планируем повторную попытку
            self._schedule_retry(recipient, step)
    
    def _should_stop_for_recipient(self, recipient: BlastRecipient) -> bool:
        """Проверяет нужно ли остановить рассылку для получателя"""
        stop_conditions = self.strategy.get('stop_on', [])
        
        for condition in stop_conditions:
            if condition == 'delivered_and_clicked':
                # Проверяем что есть доставленное и кликнутое сообщение
                if (recipient.last_clicked_at and 
                    DeliveryAttempt.objects.filter(
                        blast_recipient=recipient,
                        status__in=[DeliveryStatus.DELIVERED, DeliveryStatus.CLICKED]
                    ).exists()):
                    return True
            
            elif condition == 'redeemed':
                # Проверяем что есть погашение купона после начала рассылки
                if (recipient.converted_at and 
                    recipient.converted_at >= self.blast.started_at):
                    return True
        
        return False
    
    def _is_budget_exceeded(self, recipient: BlastRecipient) -> bool:
        """Проверяет превышен ли бюджет"""
        if self.blast.budget_cap and self.blast.current_cost >= self.blast.budget_cap:
            return True
        
        max_cost_per_recipient = self.strategy.get('max_cost_per_recipient', 0)
        if max_cost_per_recipient and recipient.total_cost >= max_cost_per_recipient:
            return True
        
        return False
    
    def _update_blast_stats(self, success: bool):
        """Обновляет статистику рассылки"""
        if success:
            Blast.objects.filter(id=self.blast.id).update(
                sent_count=F('sent_count') + 1
            )
    
    def process_pending_recipients(self):
        """Обрабатывает получателей, готовых к отправке"""
        if self.blast.status != BlastStatus.RUNNING:
            return
        
        # Проверяем бюджет
        if self.blast.budget_cap and self.blast.current_cost >= self.blast.budget_cap:
            self._complete_blast()
            return
        
        # Обрабатываем готовых получателей
        self._schedule_next_attempts()
        
        # Проверяем завершение рассылки
        pending_count = BlastRecipient.objects.filter(
            blast=self.blast,
            status__in=[BlastRecipientStatus.PENDING, BlastRecipientStatus.PROCESSING]
        ).count()
        
        if pending_count == 0:
            self._complete_blast()
    
    def _complete_blast(self):
        """Завершает рассылку"""
        self.blast.status = BlastStatus.COMPLETED
        self.blast.completed_at = timezone.now()
        self.blast.save()
        
        logger.info(f"Completed blast {self.blast.id}")
    
    def pause_blast(self):
        """Приостанавливает рассылку"""
        self.blast.status = BlastStatus.PAUSED
        self.blast.save()
        
        logger.info(f"Paused blast {self.blast.id}")
    
    def resume_blast(self):
        """Возобновляет рассылку"""
        if self.blast.status == BlastStatus.PAUSED:
            self.blast.status = BlastStatus.RUNNING
            self.blast.save()
            
            # Планируем следующие попытки
            self._schedule_next_attempts()
            
            logger.info(f"Resumed blast {self.blast.id}")
    
    def cancel_blast(self):
        """Отменяет рассылку"""
        self.blast.status = BlastStatus.CANCELLED
        self.blast.completed_at = timezone.now()
        self.blast.save()
        
        # Отменяем все ожидающие попытки
        BlastRecipient.objects.filter(
            blast=self.blast,
            status__in=[BlastRecipientStatus.PENDING, BlastRecipientStatus.PROCESSING]
        ).update(status=BlastRecipientStatus.FAILED)
        
        logger.info(f"Cancelled blast {self.blast.id}")


def process_all_pending_blasts():
    """Обрабатывает все активные рассылки"""
    running_blasts = Blast.objects.filter(status=BlastStatus.RUNNING)
    
    for blast in running_blasts:
        try:
            orchestrator = BlastOrchestrator(blast)
            orchestrator.process_pending_recipients()
        except Exception as e:
            logger.error(f"Error processing blast {blast.id}: {e}")


def process_scheduled_blasts():
    """Запускает запланированные рассылки"""
    now = timezone.now()
    
    scheduled_blasts = Blast.objects.filter(
        status=BlastStatus.SCHEDULED,
        schedule_at__lte=now
    )
    
    for blast in scheduled_blasts:
        try:
            orchestrator = BlastOrchestrator(blast)
            orchestrator.start_blast()
        except Exception as e:
            logger.error(f"Error starting scheduled blast {blast.id}: {e}")


def handle_delivery_webhook(external_id: str, status: str, metadata: Dict = None):
    """Обрабатывает webhook от провайдера о статусе доставки"""
    try:
        delivery_attempt = DeliveryAttempt.objects.get(external_id=external_id)
        
        # Обновляем статус
        old_status = delivery_attempt.status
        
        status_mapping = {
            'delivered': DeliveryStatus.DELIVERED,
            'failed': DeliveryStatus.FAILED,
            'bounced': DeliveryStatus.BOUNCED,
            'opened': DeliveryStatus.OPENED,
            'clicked': DeliveryStatus.CLICKED,
            'unsubscribed': DeliveryStatus.UNSUBSCRIBED
        }
        
        new_status = status_mapping.get(status.lower(), delivery_attempt.status)
        delivery_attempt.status = new_status
        
        # Обновляем временные метки
        now = timezone.now()
        if new_status == DeliveryStatus.DELIVERED and not delivery_attempt.delivered_at:
            delivery_attempt.delivered_at = now
        elif new_status == DeliveryStatus.OPENED and not delivery_attempt.opened_at:
            delivery_attempt.opened_at = now
        elif new_status == DeliveryStatus.CLICKED and not delivery_attempt.clicked_at:
            delivery_attempt.clicked_at = now
        
        # Обновляем метаданные
        if metadata:
            delivery_attempt.metadata.update(metadata)
        
        delivery_attempt.save()
        
        # Обновляем метрики рассылки если статус изменился
        if old_status != new_status:
            _update_blast_metrics_from_delivery(delivery_attempt, old_status, new_status)
        
        logger.info(f"Updated delivery attempt {delivery_attempt.id} status: {old_status} -> {new_status}")
        
    except DeliveryAttempt.DoesNotExist:
        logger.warning(f"Delivery attempt not found for external_id: {external_id}")


def _update_blast_metrics_from_delivery(delivery_attempt: DeliveryAttempt, old_status: str, new_status: str):
    """Обновляет метрики рассылки на основе изменения статуса доставки"""
    blast = delivery_attempt.blast_recipient.blast
    
    updates = {}
    
    if new_status == DeliveryStatus.DELIVERED and old_status != DeliveryStatus.DELIVERED:
        updates['delivered_count'] = F('delivered_count') + 1
    
    if new_status == DeliveryStatus.OPENED and old_status != DeliveryStatus.OPENED:
        updates['opened_count'] = F('opened_count') + 1
    
    if new_status == DeliveryStatus.CLICKED and old_status != DeliveryStatus.CLICKED:
        updates['clicked_count'] = F('clicked_count') + 1
    
    if updates:
        Blast.objects.filter(id=blast.id).update(**updates)
