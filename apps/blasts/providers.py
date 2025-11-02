"""
Провайдеры для отправки сообщений через различные каналы
"""

import requests
import smtplib
from abc import ABC, abstractmethod
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional
from django.conf import settings
from django.utils import timezone


class DeliveryResult:
    """Результат попытки доставки сообщения"""
    def __init__(self, success: bool, external_id: str = '', error_message: str = '', cost: float = 0.0, metadata: Dict = None):
        self.success = success
        self.external_id = external_id  # ID сообщения у провайдера
        self.error_message = error_message
        self.cost = cost
        self.metadata = metadata or {}


class BaseProvider(ABC):
    """Базовый класс для всех провайдеров"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    @abstractmethod
    def send_message(self, to: str, subject: str = '', body: str = '', **kwargs) -> DeliveryResult:
        """Отправляет сообщение"""
        pass
    
    @abstractmethod
    def get_status(self, external_id: str) -> str:
        """Получает статус сообщения по ID провайдера"""
        pass
    
    @abstractmethod
    def get_cost_per_message(self, to: str = '') -> float:
        """Возвращает стоимость отправки одного сообщения"""
        pass


class SMTPEmailProvider(BaseProvider):
    """Email провайдер через SMTP"""
    
    def send_message(self, to: str, subject: str = '', body: str = '', html_body: str = '', **kwargs) -> DeliveryResult:
        try:
            # Создаем сообщение
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.config.get('from_email', settings.DEFAULT_FROM_EMAIL)
            msg['To'] = to
            
            # Добавляем текстовую версию
            if body:
                text_part = MIMEText(body, 'plain', 'utf-8')
                msg.attach(text_part)
            
            # Добавляем HTML версию
            if html_body:
                html_part = MIMEText(html_body, 'html', 'utf-8')
                msg.attach(html_part)
            
            # Отправляем через SMTP
            with smtplib.SMTP(self.config['smtp_host'], self.config.get('smtp_port', 587)) as server:
                if self.config.get('use_tls', True):
                    server.starttls()
                
                if self.config.get('smtp_user') and self.config.get('smtp_password'):
                    server.login(self.config['smtp_user'], self.config['smtp_password'])
                
                server.send_message(msg)
            
            # Генерируем псевдо-ID для SMTP (так как нет внешнего ID)
            external_id = f"smtp_{timezone.now().timestamp()}"
            
            return DeliveryResult(
                success=True,
                external_id=external_id,
                cost=self.get_cost_per_message(),
                metadata={'provider': 'smtp', 'to': to}
            )
            
        except Exception as e:
            return DeliveryResult(
                success=False,
                error_message=str(e),
                metadata={'provider': 'smtp', 'to': to}
            )
    
    def get_status(self, external_id: str) -> str:
        # SMTP не предоставляет трекинг статуса
        return 'sent'
    
    def get_cost_per_message(self, to: str = '') -> float:
        return self.config.get('cost_per_email', 0.001)  # $0.001 по умолчанию


class SendGridProvider(BaseProvider):
    """Email провайдер через SendGrid API"""
    
    def send_message(self, to: str, subject: str = '', body: str = '', html_body: str = '', **kwargs) -> DeliveryResult:
        try:
            url = 'https://api.sendgrid.com/v3/mail/send'
            
            headers = {
                'Authorization': f'Bearer {self.config["api_key"]}',
                'Content-Type': 'application/json'
            }
            
            # Формируем содержимое
            content = []
            if body:
                content.append({'type': 'text/plain', 'value': body})
            if html_body:
                content.append({'type': 'text/html', 'value': html_body})
            
            payload = {
                'personalizations': [{
                    'to': [{'email': to}],
                    'subject': subject
                }],
                'from': {
                    'email': self.config.get('from_email', settings.DEFAULT_FROM_EMAIL),
                    'name': self.config.get('from_name', 'System')
                },
                'content': content
            }
            
            response = requests.post(url, json=payload, headers=headers)
            
            if response.status_code == 202:
                # SendGrid возвращает пустой ответ при успехе
                external_id = response.headers.get('X-Message-Id', f'sg_{timezone.now().timestamp()}')
                return DeliveryResult(
                    success=True,
                    external_id=external_id,
                    cost=self.get_cost_per_message(),
                    metadata={'provider': 'sendgrid', 'status_code': response.status_code}
                )
            else:
                return DeliveryResult(
                    success=False,
                    error_message=f'SendGrid error: {response.status_code} - {response.text}',
                    metadata={'provider': 'sendgrid', 'status_code': response.status_code}
                )
                
        except Exception as e:
            return DeliveryResult(
                success=False,
                error_message=str(e),
                metadata={'provider': 'sendgrid'}
            )
    
    def get_status(self, external_id: str) -> str:
        # Можно реализовать через SendGrid Events API
        return 'sent'
    
    def get_cost_per_message(self, to: str = '') -> float:
        return self.config.get('cost_per_email', 0.0001)  # SendGrid ~$0.0001


class TwilioSMSProvider(BaseProvider):
    """SMS провайдер через Twilio"""
    
    def send_message(self, to: str, subject: str = '', body: str = '', **kwargs) -> DeliveryResult:
        try:
            url = f'https://api.twilio.com/2010-04-01/Accounts/{self.config["account_sid"]}/Messages.json'
            
            auth = (self.config['account_sid'], self.config['auth_token'])
            
            data = {
                'From': self.config['from_number'],
                'To': to,
                'Body': body[:160]  # SMS лимит
            }
            
            response = requests.post(url, data=data, auth=auth)
            
            if response.status_code == 201:
                result = response.json()
                return DeliveryResult(
                    success=True,
                    external_id=result['sid'],
                    cost=self.get_cost_per_message(to),
                    metadata={'provider': 'twilio', 'status': result.get('status')}
                )
            else:
                return DeliveryResult(
                    success=False,
                    error_message=f'Twilio error: {response.status_code} - {response.text}',
                    metadata={'provider': 'twilio', 'status_code': response.status_code}
                )
                
        except Exception as e:
            return DeliveryResult(
                success=False,
                error_message=str(e),
                metadata={'provider': 'twilio'}
            )
    
    def get_status(self, external_id: str) -> str:
        try:
            url = f'https://api.twilio.com/2010-04-01/Accounts/{self.config["account_sid"]}/Messages/{external_id}.json'
            auth = (self.config['account_sid'], self.config['auth_token'])
            
            response = requests.get(url, auth=auth)
            if response.status_code == 200:
                result = response.json()
                return result.get('status', 'unknown')
        except:
            pass
        return 'unknown'
    
    def get_cost_per_message(self, to: str = '') -> float:
        # Стоимость зависит от направления
        if to.startswith('+7'):  # Россия/Казахстан
            return self.config.get('cost_per_sms_local', 0.05)
        return self.config.get('cost_per_sms_international', 0.1)


class InfobipSMSProvider(BaseProvider):
    """SMS провайдер через Infobip (популярен в КЗ)"""
    
    def send_message(self, to: str, subject: str = '', body: str = '', **kwargs) -> DeliveryResult:
        try:
            url = f'{self.config.get("base_url", "https://api.infobip.com")}/sms/2/text/advanced'
            
            headers = {
                'Authorization': f'App {self.config["api_key"]}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            payload = {
                'messages': [{
                    'from': self.config['from_number'],
                    'destinations': [{'to': to}],
                    'text': body[:160]
                }]
            }
            
            response = requests.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                messages = result.get('messages', [])
                if messages:
                    message = messages[0]
                    return DeliveryResult(
                        success=True,
                        external_id=message.get('messageId', ''),
                        cost=self.get_cost_per_message(to),
                        metadata={'provider': 'infobip', 'status': message.get('status')}
                    )
            
            return DeliveryResult(
                success=False,
                error_message=f'Infobip error: {response.status_code} - {response.text}',
                metadata={'provider': 'infobip', 'status_code': response.status_code}
            )
            
        except Exception as e:
            return DeliveryResult(
                success=False,
                error_message=str(e),
                metadata={'provider': 'infobip'}
            )
    
    def get_status(self, external_id: str) -> str:
        try:
            url = f'{self.config.get("base_url", "https://api.infobip.com")}/sms/1/reports'
            headers = {
                'Authorization': f'App {self.config["api_key"]}',
                'Accept': 'application/json'
            }
            
            params = {'messageId': external_id}
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                result = response.json()
                reports = result.get('results', [])
                if reports:
                    return reports[0].get('status', {}).get('name', 'unknown').lower()
        except:
            pass
        return 'unknown'
    
    def get_cost_per_message(self, to: str = '') -> float:
        if to.startswith('+7'):  # КЗ/РУ направления
            return self.config.get('cost_per_sms_local', 0.03)
        return self.config.get('cost_per_sms_international', 0.08)


class WhatsAppCloudProvider(BaseProvider):
    """WhatsApp Business через Meta Cloud API"""
    
    def send_message(self, to: str, subject: str = '', body: str = '', template_name: str = '', template_params: list = None, **kwargs) -> DeliveryResult:
        try:
            phone_number_id = self.config['phone_number_id']
            url = f'https://graph.facebook.com/v18.0/{phone_number_id}/messages'
            
            headers = {
                'Authorization': f'Bearer {self.config["access_token"]}',
                'Content-Type': 'application/json'
            }
            
            # Формируем сообщение
            if template_name:
                # Шаблонное сообщение (HSM)
                message_data = {
                    'messaging_product': 'whatsapp',
                    'to': to,
                    'type': 'template',
                    'template': {
                        'name': template_name,
                        'language': {'code': self.config.get('language_code', 'ru')},
                        'components': []
                    }
                }
                
                if template_params:
                    message_data['template']['components'].append({
                        'type': 'body',
                        'parameters': [{'type': 'text', 'text': param} for param in template_params]
                    })
            else:
                # Обычное текстовое сообщение (только в рамках 24-часового окна)
                message_data = {
                    'messaging_product': 'whatsapp',
                    'to': to,
                    'type': 'text',
                    'text': {'body': body[:1000]}  # WhatsApp лимит
                }
            
            response = requests.post(url, json=message_data, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                messages = result.get('messages', [])
                if messages:
                    return DeliveryResult(
                        success=True,
                        external_id=messages[0]['id'],
                        cost=self.get_cost_per_message(to),
                        metadata={'provider': 'whatsapp_cloud', 'wamid': messages[0]['id']}
                    )
            
            return DeliveryResult(
                success=False,
                error_message=f'WhatsApp error: {response.status_code} - {response.text}',
                metadata={'provider': 'whatsapp_cloud', 'status_code': response.status_code}
            )
            
        except Exception as e:
            return DeliveryResult(
                success=False,
                error_message=str(e),
                metadata={'provider': 'whatsapp_cloud'}
            )
    
    def get_status(self, external_id: str) -> str:
        # WhatsApp статусы приходят через webhook
        return 'sent'
    
    def get_cost_per_message(self, to: str = '') -> float:
        return self.config.get('cost_per_message', 0.05)  # ~$0.05 за HSM


class DummyProvider(BaseProvider):
    """Заглушка для тестирования"""
    
    def send_message(self, to: str, subject: str = '', body: str = '', **kwargs) -> DeliveryResult:
        import time
        time.sleep(0.1)  # Имитация задержки
        
        return DeliveryResult(
            success=True,
            external_id=f'dummy_{timezone.now().timestamp()}',
            cost=0.01,
            metadata={'provider': 'dummy', 'to': to, 'body_length': len(body)}
        )
    
    def get_status(self, external_id: str) -> str:
        return 'delivered'
    
    def get_cost_per_message(self, to: str = '') -> float:
        return 0.01


# Фабрика провайдеров
def get_provider(channel: str, config: Dict[str, Any]) -> BaseProvider:
    """Создает провайдер для указанного канала"""
    
    providers = {
        'email': {
            'smtp': SMTPEmailProvider,
            'sendgrid': SendGridProvider,
        },
        'sms': {
            'twilio': TwilioSMSProvider,
            'infobip': InfobipSMSProvider,
        },
        'whatsapp': {
            'cloud': WhatsAppCloudProvider,
        }
    }
    
    provider_type = config.get('provider_type', 'dummy')
    
    if channel in providers and provider_type in providers[channel]:
        return providers[channel][provider_type](config)
    
    # Возвращаем dummy провайдер для тестирования
    return DummyProvider(config)


# Настройки провайдеров по умолчанию
DEFAULT_PROVIDER_CONFIGS = {
    'email': {
        'provider_type': 'smtp',
        'smtp_host': 'localhost',
        'smtp_port': 587,
        'use_tls': True,
        'from_email': 'noreply@example.com',
        'cost_per_email': 0.001
    },
    'sms': {
        'provider_type': 'dummy',
        'cost_per_sms_local': 0.05,
        'cost_per_sms_international': 0.1
    },
    'whatsapp': {
        'provider_type': 'cloud',
        'language_code': 'ru',
        'cost_per_message': 0.05
    }
}
