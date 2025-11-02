"""
Сервисы для работы с омниканальными рассылками
"""

from typing import List, Dict, Any, Optional
from django.utils import timezone
from django.db.models import Q
from datetime import timedelta, datetime
import hashlib
import re

from .models import (
    ContactPoint, ContactPointType, MessageTemplate, Blast, BlastStatus,
    BlastRecipient, BlastRecipientStatus, DeliveryAttempt, DeliveryStatus,
    ShortLink, ShortLinkClick, MessagePreference
)
from .providers import get_provider, DEFAULT_PROVIDER_CONFIGS


def get_or_create_contact_point(business, customer, contact_type: str, value: str, **kwargs) -> ContactPoint:
    """Создает или получает точку контакта"""
    contact_point, created = ContactPoint.objects.get_or_create(
        business=business,
        type=contact_type,
        value=value,
        defaults={
            'customer': customer,
            'verified': kwargs.get('verified', False),
            'opt_in': kwargs.get('opt_in', True),
            **kwargs
        }
    )
    
    # Обновляем customer если он не был установлен
    if not contact_point.customer and customer:
        contact_point.customer = customer
        contact_point.save(update_fields=['customer'])
    
    return contact_point


def collect_contact_points_for_customer(business, customer) -> Dict[str, List[ContactPoint]]:
    """Собирает все контактные точки клиента по каналам"""
    points = ContactPoint.objects.filter(
        business=business,
        customer=customer,
        opt_in=True
    ).select_related('customer')
    
    result = {}
    for point in points:
        if point.type not in result:
            result[point.type] = []
        result[point.type].append(point)
    
    return result


def create_blast_recipients(blast: Blast) -> int:
    """Создает получателей рассылки на основе сегмента"""
    from apps.customers.models import Customer
    
    # Получаем клиентов из сегмента
    if blast.segment:
        from apps.segments.models import SegmentMember
        segment_members = SegmentMember.objects.filter(segment=blast.segment)
        customer_ids = segment_members.values_list('customer_id', flat=True)
        customers = Customer.objects.filter(
            business=blast.business,
            id__in=customer_ids
        )
    else:
        # Если сегмент не указан, берем всех клиентов бизнеса
        customers = Customer.objects.filter(business=blast.business)
    
    # Применяем дополнительные фильтры
    if blast.custom_filter:
        # Здесь можно добавить логику обработки кастомных фильтров
        pass
    
    recipients_created = 0
    
    for customer in customers:
        # Собираем контактные точки
        contact_points_by_type = collect_contact_points_for_customer(blast.business, customer)
        
        if not contact_points_by_type:
            continue  # Пропускаем клиентов без контактов
        
        # Определяем приоритет каналов из стратегии рассылки
        strategy = blast.strategy or {}
        cascade = strategy.get('cascade', [
            {'channel': 'whatsapp', 'timeout_min': 60},
            {'channel': 'sms', 'timeout_min': 180},
            {'channel': 'email', 'timeout_min': 0}
        ])
        
        # Формируем список контактных точек в порядке приоритета
        ordered_contact_points = []
        for step in cascade:
            channel = step['channel']
            if channel in contact_points_by_type:
                # Берем первую доступную точку контакта этого типа
                ordered_contact_points.append(contact_points_by_type[channel][0].id)
        
        if ordered_contact_points:
            # Создаем получателя
            BlastRecipient.objects.get_or_create(
                blast=blast,
                customer=customer,
                defaults={
                    'contact_points': ordered_contact_points,
                    'status': BlastRecipientStatus.PENDING,
                    'next_attempt_at': timezone.now()
                }
            )
            recipients_created += 1
    
    # Обновляем счетчик в рассылке
    blast.total_recipients = recipients_created
    blast.save(update_fields=['total_recipients'])
    
    return recipients_created


def render_message_template(template: MessageTemplate, context: Dict[str, Any]) -> Dict[str, str]:
    """Рендерит шаблон сообщения с подстановкой переменных"""
    
    def replace_variables(text: str) -> str:
        if not text:
            return text
        
        # Простая подстановка переменных вида {{variable_name}}
        for key, value in context.items():
            pattern = f'{{{{{key}}}}}'
            text = text.replace(pattern, str(value))
        
        return text
    
    return {
        'subject': replace_variables(template.subject),
        'body': replace_variables(template.body_text),
        'html_body': replace_variables(template.body_html) if template.body_html else ''
    }


def create_short_link(business, original_url: str, blast: Blast = None, delivery_attempt = None, utm_params: Dict = None) -> ShortLink:
    """Создает короткую ссылку для трекинга"""
    
    # Генерируем уникальный код
    while True:
        short_code = ShortLink.generate_code()
        if not ShortLink.objects.filter(short_code=short_code).exists():
            break
    
    utm_params = utm_params or {}
    
    short_link = ShortLink.objects.create(
        business=business,
        short_code=short_code,
        original_url=original_url,
        blast=blast,
        delivery_attempt=delivery_attempt,
        utm_source=utm_params.get('utm_source', ''),
        utm_medium=utm_params.get('utm_medium', ''),
        utm_campaign=utm_params.get('utm_campaign', ''),
        utm_content=utm_params.get('utm_content', '')
    )
    
    return short_link


def process_short_link_click(short_code: str, request) -> Optional[str]:
    """Обрабатывает клик по короткой ссылке"""
    try:
        short_link = ShortLink.objects.get(short_code=short_code, is_active=True)
        
        # Проверяем срок действия
        if short_link.expires_at and timezone.now() > short_link.expires_at:
            return None
        
        # Собираем информацию о клике
        ip_address = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR', '')
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        referer = request.META.get('HTTP_REFERER', '')
        
        # Создаем отпечаток для определения уникальности
        fingerprint_data = f"{ip_address}:{user_agent}:{short_link.id}"
        fingerprint = hashlib.md5(fingerprint_data.encode()).hexdigest()
        
        # Определяем уникальность клика
        is_unique = not ShortLinkClick.objects.filter(
            short_link=short_link,
            fingerprint=fingerprint
        ).exists()
        
        # Создаем запись о клике
        ShortLinkClick.objects.create(
            short_link=short_link,
            ip_address=ip_address,
            user_agent=user_agent,
            referer=referer,
            fingerprint=fingerprint
        )
        
        # Обновляем счетчики
        short_link.clicks_count += 1
        if is_unique:
            short_link.unique_clicks_count += 1
        short_link.save(update_fields=['clicks_count', 'unique_clicks_count'])
        
        # Обновляем метрики рассылки и получателя
        if short_link.delivery_attempt:
            # Отмечаем клик в попытке доставки
            delivery_attempt = short_link.delivery_attempt
            if not delivery_attempt.clicked_at:
                delivery_attempt.clicked_at = timezone.now()
                delivery_attempt.status = DeliveryStatus.CLICKED
                delivery_attempt.save(update_fields=['clicked_at', 'status'])
                
                # Обновляем метрики получателя
                blast_recipient = delivery_attempt.blast_recipient
                if not blast_recipient.last_clicked_at:
                    blast_recipient.last_clicked_at = timezone.now()
                    blast_recipient.save(update_fields=['last_clicked_at'])
                    
                    # Обновляем метрики рассылки
                    if short_link.blast:
                        Blast.objects.filter(id=short_link.blast.id).update(
                            clicked_count=models.F('clicked_count') + 1
                        )
        
        return short_link.original_url
        
    except ShortLink.DoesNotExist:
        return None


def send_message_via_provider(delivery_attempt: DeliveryAttempt) -> bool:
    """Отправляет сообщение через провайдера"""
    
    # Получаем конфигурацию провайдера
    business = delivery_attempt.blast_recipient.blast.business
    provider_config = business.settings.get('providers', {}).get(delivery_attempt.channel)
    
    if not provider_config:
        # Используем конфигурацию по умолчанию
        provider_config = DEFAULT_PROVIDER_CONFIGS.get(delivery_attempt.channel, {})
    
    # Создаем провайдер
    provider = get_provider(delivery_attempt.channel, provider_config)
    
    # Подготавливаем контекст для рендеринга
    blast_recipient = delivery_attempt.blast_recipient
    customer = blast_recipient.customer
    blast = blast_recipient.blast
    
    context = {
        'customer_phone': customer.phone_e164,
        'customer_first_name': customer.tags.get('first_name', ''),
        'business_name': business.name,
        'blast_name': blast.name
    }
    
    # Если есть связанный купон, добавляем его данные
    if hasattr(customer, 'coupons') and customer.coupons.filter(status='active').exists():
        coupon = customer.coupons.filter(status='active').first()
        context.update({
            'coupon_code': coupon.code,
            'coupon_expires_at': coupon.expires_at.strftime('%d.%m.%Y') if coupon.expires_at else ''
        })
    
    # Рендерим шаблон если он есть
    if delivery_attempt.template:
        rendered = render_message_template(delivery_attempt.template, context)
        subject = rendered['subject']
        body = rendered['body']
        html_body = rendered['html_body']
    else:
        subject = delivery_attempt.subject
        body = delivery_attempt.body
        html_body = ''
    
    # Обрабатываем ссылки в тексте (создаем короткие ссылки)
    body = process_links_in_text(body, business, blast, delivery_attempt)
    html_body = process_links_in_text(html_body, business, blast, delivery_attempt)
    
    # Отправляем сообщение
    result = provider.send_message(
        to=delivery_attempt.contact_point.value,
        subject=subject,
        body=body,
        html_body=html_body
    )
    
    # Обновляем попытку доставки
    delivery_attempt.external_id = result.external_id
    delivery_attempt.cost = result.cost
    delivery_attempt.metadata.update(result.metadata)
    
    if result.success:
        delivery_attempt.status = DeliveryStatus.SENT
        delivery_attempt.sent_at = timezone.now()
    else:
        delivery_attempt.status = DeliveryStatus.FAILED
        delivery_attempt.error_message = result.error_message
    
    delivery_attempt.save()
    
    return result.success


def process_links_in_text(text: str, business, blast: Blast, delivery_attempt) -> str:
    """Заменяет ссылки в тексте на короткие ссылки для трекинга"""
    if not text:
        return text
    
    # Простой regex для поиска URL
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    
    def replace_url(match):
        original_url = match.group(0)
        
        # Создаем короткую ссылку
        short_link = create_short_link(
            business=business,
            original_url=original_url,
            blast=blast,
            delivery_attempt=delivery_attempt,
            utm_params={
                'utm_source': delivery_attempt.channel,
                'utm_medium': 'blast',
                'utm_campaign': blast.name
            }
        )
        
        return short_link.get_short_url()
    
    return re.sub(url_pattern, replace_url, text)


def get_message_preferences(business, customer) -> MessagePreference:
    """Получает предпочтения клиента по сообщениям"""
    preferences, created = MessagePreference.objects.get_or_create(
        business=business,
        customer=customer,
        defaults={
            'locale': 'ru',
            'preferred_channels': ['whatsapp', 'sms', 'email'],
            'max_messages_per_day': 3,
            'max_messages_per_week': 10
        }
    )
    return preferences


def check_quiet_hours(preferences: MessagePreference) -> bool:
    """Проверяет, находимся ли мы в тихих часах"""
    from django.utils import timezone
    import pytz
    
    try:
        tz = pytz.timezone(preferences.timezone)
        now = timezone.now().astimezone(tz)
        current_time = now.time()
        
        start = preferences.quiet_hours_start
        end = preferences.quiet_hours_end
        
        if start <= end:
            # Обычный интервал (например, 21:00 - 09:00 следующего дня)
            return start <= current_time <= end
        else:
            # Интервал через полночь (например, 21:00 - 09:00)
            return current_time >= start or current_time <= end
            
    except:
        return False


def check_frequency_limits(business, customer, channel: str) -> bool:
    """Проверяет лимиты частоты отправки"""
    preferences = get_message_preferences(business, customer)
    
    now = timezone.now()
    
    # Проверяем дневной лимит
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_count = DeliveryAttempt.objects.filter(
        blast_recipient__blast__business=business,
        blast_recipient__customer=customer,
        channel=channel,
        created_at__gte=day_start,
        status__in=[DeliveryStatus.SENT, DeliveryStatus.DELIVERED]
    ).count()
    
    if daily_count >= preferences.max_messages_per_day:
        return False
    
    # Проверяем недельный лимит
    week_start = now - timedelta(days=7)
    weekly_count = DeliveryAttempt.objects.filter(
        blast_recipient__blast__business=business,
        blast_recipient__customer=customer,
        channel=channel,
        created_at__gte=week_start,
        status__in=[DeliveryStatus.SENT, DeliveryStatus.DELIVERED]
    ).count()
    
    if weekly_count >= preferences.max_messages_per_week:
        return False
    
    return True


def get_blast_analytics(blast: Blast) -> Dict[str, Any]:
    """Возвращает аналитику по рассылке"""
    
    # Базовые метрики
    analytics = {
        'total_recipients': blast.total_recipients,
        'sent_count': blast.sent_count,
        'delivered_count': blast.delivered_count,
        'opened_count': blast.opened_count,
        'clicked_count': blast.clicked_count,
        'converted_count': blast.converted_count,
        'current_cost': float(blast.current_cost),
        'delivery_rate': blast.delivery_rate(),
        'conversion_rate': blast.conversion_rate()
    }
    
    # Метрики по каналам
    channel_stats = {}
    delivery_attempts = DeliveryAttempt.objects.filter(blast_recipient__blast=blast)
    
    for channel_type in ContactPointType.choices:
        channel = channel_type[0]
        channel_attempts = delivery_attempts.filter(channel=channel)
        
        if channel_attempts.exists():
            total = channel_attempts.count()
            sent = channel_attempts.filter(status__in=[DeliveryStatus.SENT, DeliveryStatus.DELIVERED]).count()
            delivered = channel_attempts.filter(status=DeliveryStatus.DELIVERED).count()
            clicked = channel_attempts.filter(status=DeliveryStatus.CLICKED).count()
            cost = sum(float(attempt.cost) for attempt in channel_attempts)
            
            channel_stats[channel] = {
                'total': total,
                'sent': sent,
                'delivered': delivered,
                'clicked': clicked,
                'cost': cost,
                'delivery_rate': (delivered / sent * 100) if sent > 0 else 0,
                'click_rate': (clicked / delivered * 100) if delivered > 0 else 0
            }
    
    analytics['channels'] = channel_stats
    
    # Временная динамика (по дням)
    from django.db.models import Count, Q
    from django.db.models.functions import TruncDate
    
    daily_stats = delivery_attempts.extra(
        select={'date': 'DATE(blasts_deliveryattempt.created_at)'}
    ).values('date').annotate(
        sent=Count('id', filter=Q(status__in=[DeliveryStatus.SENT, DeliveryStatus.DELIVERED])),
        delivered=Count('id', filter=Q(status=DeliveryStatus.DELIVERED)),
        clicked=Count('id', filter=Q(status=DeliveryStatus.CLICKED))
    ).order_by('date')
    
    analytics['daily_stats'] = list(daily_stats)
    
    return analytics
