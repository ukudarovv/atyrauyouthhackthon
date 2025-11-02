"""
Обработчики webhook'ов от провайдеров рассылок
"""

import json
import logging
from typing import Dict, Any, Optional
from django.http import HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpResponse
from django.utils import timezone

from .models import DeliveryAttempt, DeliveryStatus
from .orchestrator import handle_delivery_webhook
from .tasks import handle_delivery_webhook_task, run_sync_fallback

logger = logging.getLogger(__name__)


class WebhookProcessor:
    """Базовый класс для обработки webhook'ов"""
    
    def __init__(self, request: HttpRequest):
        self.request = request
        self.headers = request.headers
        self.body = request.body
        
    def verify_signature(self) -> bool:
        """Проверяет подпись webhook'а"""
        return True  # Базовая реализация - переопределить в наследниках
    
    def parse_payload(self) -> Dict[str, Any]:
        """Парсит payload webhook'а"""
        try:
            return json.loads(self.body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to parse webhook payload: {e}")
            return {}
    
    def process(self) -> Dict[str, Any]:
        """Обрабатывает webhook"""
        raise NotImplementedError


class SendGridWebhookProcessor(WebhookProcessor):
    """Обработчик webhook'ов от SendGrid"""
    
    def verify_signature(self) -> bool:
        """Проверяет подпись SendGrid"""
        # Здесь должна быть проверка подписи SendGrid
        # signature = self.headers.get('X-Twilio-Email-Event-Webhook-Signature')
        return True
    
    def process(self) -> Dict[str, Any]:
        """Обрабатывает события от SendGrid"""
        if not self.verify_signature():
            return {'success': False, 'error': 'Invalid signature'}
        
        payload = self.parse_payload()
        if not payload:
            return {'success': False, 'error': 'Invalid payload'}
        
        processed_count = 0
        
        # SendGrid отправляет массив событий
        events = payload if isinstance(payload, list) else [payload]
        
        for event in events:
            try:
                external_id = event.get('sg_message_id')  # ID сообщения в SendGrid
                event_type = event.get('event')  # delivered, bounce, open, click, etc.
                timestamp = event.get('timestamp')
                
                if not external_id or not event_type:
                    continue
                
                # Маппинг событий SendGrid на наши статусы
                status_mapping = {
                    'delivered': 'delivered',
                    'bounce': 'bounced',
                    'dropped': 'failed',
                    'open': 'opened',
                    'click': 'clicked',
                    'unsubscribe': 'unsubscribed',
                    'spamreport': 'failed'
                }
                
                status = status_mapping.get(event_type)
                if not status:
                    continue
                
                # Дополнительные метаданные
                metadata = {
                    'provider': 'sendgrid',
                    'event_type': event_type,
                    'timestamp': timestamp,
                    'reason': event.get('reason', ''),
                    'url': event.get('url', ''),  # Для кликов
                    'ip': event.get('ip', ''),
                    'useragent': event.get('useragent', '')
                }
                
                # Обрабатываем асинхронно
                run_sync_fallback(handle_delivery_webhook_task, external_id, status, metadata)
                processed_count += 1
                
            except Exception as e:
                logger.error(f"Error processing SendGrid event: {e}")
                continue
        
        return {'success': True, 'processed': processed_count}


class TwilioWebhookProcessor(WebhookProcessor):
    """Обработчик webhook'ов от Twilio SMS"""
    
    def verify_signature(self) -> bool:
        """Проверяет подпись Twilio"""
        # Здесь должна быть проверка подписи Twilio
        # signature = self.headers.get('X-Twilio-Signature')
        return True
    
    def process(self) -> Dict[str, Any]:
        """Обрабатывает статусы SMS от Twilio"""
        if not self.verify_signature():
            return {'success': False, 'error': 'Invalid signature'}
        
        # Twilio отправляет данные как form data
        data = dict(self.request.POST.items())
        
        message_sid = data.get('MessageSid')  # ID сообщения в Twilio
        message_status = data.get('MessageStatus')  # queued, sent, delivered, failed, etc.
        
        if not message_sid or not message_status:
            return {'success': False, 'error': 'Missing required fields'}
        
        # Маппинг статусов Twilio
        status_mapping = {
            'queued': 'queued',
            'sent': 'sent',
            'delivered': 'delivered',
            'failed': 'failed',
            'undelivered': 'failed'
        }
        
        status = status_mapping.get(message_status, message_status)
        
        # Дополнительные метаданные
        metadata = {
            'provider': 'twilio',
            'message_status': message_status,
            'error_code': data.get('ErrorCode', ''),
            'error_message': data.get('ErrorMessage', ''),
            'price': data.get('Price', ''),
            'price_unit': data.get('PriceUnit', '')
        }
        
        # Обрабатываем
        try:
            run_sync_fallback(handle_delivery_webhook_task, message_sid, status, metadata)
            return {'success': True}
        except Exception as e:
            logger.error(f"Error processing Twilio webhook: {e}")
            return {'success': False, 'error': str(e)}


class InfobipWebhookProcessor(WebhookProcessor):
    """Обработчик webhook'ов от Infobip SMS"""
    
    def verify_signature(self) -> bool:
        """Проверяет подпись Infobip"""
        # Infobip может использовать Basic Auth или подпись
        return True
    
    def process(self) -> Dict[str, Any]:
        """Обрабатывает отчеты о доставке от Infobip"""
        if not self.verify_signature():
            return {'success': False, 'error': 'Invalid signature'}
        
        payload = self.parse_payload()
        if not payload:
            return {'success': False, 'error': 'Invalid payload'}
        
        processed_count = 0
        
        # Infobip отправляет массив отчетов
        reports = payload.get('results', [])
        
        for report in reports:
            try:
                message_id = report.get('messageId')
                status_info = report.get('status', {})
                status_name = status_info.get('name', '').lower()
                
                if not message_id or not status_name:
                    continue
                
                # Маппинг статусов Infobip
                status_mapping = {
                    'delivered': 'delivered',
                    'pending': 'sent',
                    'undeliverable': 'failed',
                    'expired': 'failed',
                    'rejected': 'failed'
                }
                
                status = status_mapping.get(status_name, status_name)
                
                # Дополнительные метаданные
                metadata = {
                    'provider': 'infobip',
                    'status_name': status_name,
                    'status_id': status_info.get('id'),
                    'description': status_info.get('description', ''),
                    'price': report.get('price', {}).get('pricePerMessage', 0)
                }
                
                run_sync_fallback(handle_delivery_webhook_task, message_id, status, metadata)
                processed_count += 1
                
            except Exception as e:
                logger.error(f"Error processing Infobip report: {e}")
                continue
        
        return {'success': True, 'processed': processed_count}


class WhatsAppWebhookProcessor(WebhookProcessor):
    """Обработчик webhook'ов от WhatsApp Business API"""
    
    def verify_signature(self) -> bool:
        """Проверяет подпись Meta/Facebook"""
        # signature = self.headers.get('X-Hub-Signature-256')
        return True
    
    def process(self) -> Dict[str, Any]:
        """Обрабатывает статусы сообщений WhatsApp"""
        if not self.verify_signature():
            return {'success': False, 'error': 'Invalid signature'}
        
        payload = self.parse_payload()
        if not payload:
            return {'success': False, 'error': 'Invalid payload'}
        
        processed_count = 0
        
        # WhatsApp webhook структура
        entry = payload.get('entry', [])
        
        for entry_item in entry:
            changes = entry_item.get('changes', [])
            
            for change in changes:
                value = change.get('value', {})
                statuses = value.get('statuses', [])
                
                for status_item in statuses:
                    try:
                        message_id = status_item.get('id')  # WAMID
                        status_value = status_item.get('status')  # sent, delivered, read, failed
                        
                        if not message_id or not status_value:
                            continue
                        
                        # Маппинг статусов WhatsApp
                        status_mapping = {
                            'sent': 'sent',
                            'delivered': 'delivered',
                            'read': 'opened',
                            'failed': 'failed'
                        }
                        
                        status = status_mapping.get(status_value, status_value)
                        
                        # Дополнительные метаданные
                        metadata = {
                            'provider': 'whatsapp_cloud',
                            'status': status_value,
                            'timestamp': status_item.get('timestamp'),
                            'recipient_id': status_item.get('recipient_id', ''),
                            'conversation': status_item.get('conversation', {}),
                            'pricing': status_item.get('pricing', {})
                        }
                        
                        # Обработка ошибок
                        if 'errors' in status_item:
                            metadata['errors'] = status_item['errors']
                        
                        run_sync_fallback(handle_delivery_webhook_task, message_id, status, metadata)
                        processed_count += 1
                        
                    except Exception as e:
                        logger.error(f"Error processing WhatsApp status: {e}")
                        continue
        
        return {'success': True, 'processed': processed_count}


def get_webhook_processor(request: HttpRequest, provider: str) -> Optional[WebhookProcessor]:
    """Возвращает обработчик webhook'а для указанного провайдера"""
    
    processors = {
        'sendgrid': SendGridWebhookProcessor,
        'twilio': TwilioWebhookProcessor,
        'infobip': InfobipWebhookProcessor,
        'whatsapp': WhatsAppWebhookProcessor,
    }
    
    processor_class = processors.get(provider.lower())
    if processor_class:
        return processor_class(request)
    
    return None


@csrf_exempt
@require_http_methods(["POST"])
def sendgrid_webhook(request):
    """Endpoint для webhook'ов SendGrid"""
    processor = SendGridWebhookProcessor(request)
    result = processor.process()
    
    if result['success']:
        return JsonResponse(result)
    else:
        return JsonResponse(result, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def twilio_webhook(request):
    """Endpoint для webhook'ов Twilio"""
    processor = TwilioWebhookProcessor(request)
    result = processor.process()
    
    if result['success']:
        return HttpResponse('OK')  # Twilio ожидает простой ответ
    else:
        return HttpResponse('ERROR', status=400)


@csrf_exempt
@require_http_methods(["POST"])
def infobip_webhook(request):
    """Endpoint для webhook'ов Infobip"""
    processor = InfobipWebhookProcessor(request)
    result = processor.process()
    
    if result['success']:
        return JsonResponse(result)
    else:
        return JsonResponse(result, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def whatsapp_webhook(request):
    """Endpoint для webhook'ов WhatsApp"""
    # Проверка верификации (GET запрос)
    if request.method == 'GET':
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')
        
        # Проверяем токен верификации
        expected_token = 'your_webhook_verify_token'  # Из настроек
        
        if mode == 'subscribe' and token == expected_token:
            return HttpResponse(challenge)
        else:
            return HttpResponse('Forbidden', status=403)
    
    # Обработка POST запроса
    processor = WhatsAppWebhookProcessor(request)
    result = processor.process()
    
    if result['success']:
        return JsonResponse({'status': 'ok'})
    else:
        return JsonResponse(result, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def generic_delivery_webhook(request):
    """Универсальный endpoint для webhook'ов доставки"""
    try:
        # Определяем провайдера по заголовкам или параметрам
        provider = None
        
        # SendGrid
        if 'X-Twilio-Email-Event-Webhook-Signature' in request.headers:
            provider = 'sendgrid'
        # Twilio
        elif 'X-Twilio-Signature' in request.headers:
            provider = 'twilio'
        # WhatsApp
        elif 'X-Hub-Signature-256' in request.headers:
            provider = 'whatsapp'
        # Infobip или другие
        else:
            # Пытаемся определить по User-Agent или другим заголовкам
            user_agent = request.headers.get('User-Agent', '').lower()
            if 'infobip' in user_agent:
                provider = 'infobip'
        
        # Получаем процессор
        processor = get_webhook_processor(request, provider) if provider else None
        
        if processor:
            result = processor.process()
            logger.info(f"Processed {provider} webhook: {result}")
            return JsonResponse(result)
        else:
            # Fallback - пытаемся обработать как простой JSON
            try:
                data = json.loads(request.body.decode('utf-8'))
                external_id = data.get('external_id') or data.get('message_id') or data.get('id')
                status = data.get('status') or data.get('event')
                
                if external_id and status:
                    handle_delivery_webhook(external_id, status, data)
                    return JsonResponse({'success': True})
                
            except Exception as e:
                logger.error(f"Failed to process generic webhook: {e}")
            
            return JsonResponse({'success': False, 'error': 'Unknown provider'}, status=400)
    
    except Exception as e:
        logger.error(f"Error in generic delivery webhook: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
