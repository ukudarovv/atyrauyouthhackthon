"""
Сервисы для работы с Instagram Graph API
"""
import requests
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import IGAccount, IGMedia, IGComment, IGThreadMessage

logger = logging.getLogger(__name__)

# Константы API
GRAPH_API_BASE = getattr(settings, 'GRAPH_API_BASE', 'https://graph.facebook.com/v20.0')
API_TIMEOUT = 30


class InstagramAPIError(Exception):
    """Базовая ошибка Instagram API"""
    pass


class InstagramAPIService:
    """
    Сервис для работы с Instagram Graph API
    """
    
    def __init__(self, account: IGAccount):
        self.account = account
        self.access_token = account.get_access_token()
        self.ig_user_id = account.ig_user_id
    
    def _make_request(self, method: str, endpoint: str, data: dict = None, params: dict = None) -> dict:
        """
        Выполняет запрос к Instagram Graph API
        """
        url = f"{GRAPH_API_BASE}/{endpoint}"
        
        # Добавляем access_token к параметрам
        if params is None:
            params = {}
        params['access_token'] = self.access_token
        
        try:
            if method.upper() == 'GET':
                response = requests.get(url, params=params, timeout=API_TIMEOUT)
            else:
                response = requests.post(url, data=data, params=params, timeout=API_TIMEOUT)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Instagram API request failed: {e}")
            raise InstagramAPIError(f"API request failed: {str(e)}")
        except json.JSONDecodeError as e:
            logger.error(f"Instagram API response parsing failed: {e}")
            raise InstagramAPIError(f"Invalid API response: {str(e)}")
    
    def get_account_info(self) -> dict:
        """
        Получает информацию об аккаунте
        """
        return self._make_request(
            'GET', 
            self.ig_user_id,
            params={
                'fields': 'id,username,account_type,media_count,followers_count,follows_count,profile_picture_url'
            }
        )
    
    def create_media_container(
        self, 
        media_type: str,
        media_url: str = None,
        image_url: str = None,
        video_url: str = None,
        caption: str = None,
        children: List[str] = None,
        is_reel: bool = False
    ) -> str:
        """
        Создает контейнер для медиа
        """
        data = {
            'caption': caption or ''
        }
        
        if children:
            # Карусель
            data.update({
                'media_type': 'CAROUSEL',
                'children': ','.join(children)
            })
        elif video_url or (media_url and media_type == 'video'):
            # Видео или Reel
            data['video_url'] = video_url or media_url
            if is_reel:
                data['media_type'] = 'REELS'
        else:
            # Изображение
            data['image_url'] = image_url or media_url
        
        response = self._make_request('POST', f"{self.ig_user_id}/media", data=data)
        return response['id']  # creation_id
    
    def publish_media(self, creation_id: str) -> str:
        """
        Публикует медиа контейнер
        """
        response = self._make_request(
            'POST', 
            f"{self.ig_user_id}/media_publish",
            data={'creation_id': creation_id}
        )
        return response['id']  # ig_media_id
    
    def get_media_info(self, ig_media_id: str) -> dict:
        """
        Получает информацию о медиа
        """
        return self._make_request(
            'GET',
            ig_media_id,
            params={
                'fields': 'id,media_type,media_url,permalink,caption,timestamp,like_count,comments_count,thumbnail_url'
            }
        )
    
    def get_media_insights(self, ig_media_id: str, media_type: str = 'photo') -> dict:
        """
        Получает метрики медиа
        """
        # Метрики зависят от типа медиа
        if media_type.lower() == 'reel':
            metrics = ['reach', 'impressions', 'likes', 'comments', 'saves', 'shares', 'plays']
        elif media_type.lower() == 'video':
            metrics = ['reach', 'impressions', 'likes', 'comments', 'saves', 'video_views']
        else:
            metrics = ['reach', 'impressions', 'likes', 'comments', 'saves']
        
        try:
            response = self._make_request(
                'GET',
                f"{ig_media_id}/insights",
                params={'metric': ','.join(metrics)}
            )
            
            # Преобразуем ответ в удобный формат
            insights = {}
            for item in response.get('data', []):
                metric_name = item['name']
                metric_value = item['values'][0]['value'] if item['values'] else 0
                insights[metric_name] = metric_value
            
            return insights
            
        except InstagramAPIError as e:
            logger.warning(f"Failed to get insights for media {ig_media_id}: {e}")
            return {}
    
    def get_media_comments(self, ig_media_id: str, limit: int = 100) -> List[dict]:
        """
        Получает комментарии к медиа
        """
        try:
            response = self._make_request(
                'GET',
                f"{ig_media_id}/comments",
                params={
                    'fields': 'id,text,username,timestamp,like_count,parent_id',
                    'limit': limit
                }
            )
            return response.get('data', [])
        except InstagramAPIError as e:
            logger.warning(f"Failed to get comments for media {ig_media_id}: {e}")
            return []
    
    def hide_comment(self, ig_comment_id: str, hide: bool = True) -> bool:
        """
        Скрывает или показывает комментарий
        """
        try:
            self._make_request(
                'POST',
                ig_comment_id,
                data={'hidden': 'true' if hide else 'false'}
            )
            return True
        except InstagramAPIError as e:
            logger.error(f"Failed to hide comment {ig_comment_id}: {e}")
            return False
    
    def delete_comment(self, ig_comment_id: str) -> bool:
        """
        Удаляет комментарий
        """
        try:
            self._make_request('DELETE', ig_comment_id)
            return True
        except InstagramAPIError as e:
            logger.error(f"Failed to delete comment {ig_comment_id}: {e}")
            return False
    
    def reply_to_comment(self, ig_comment_id: str, message: str) -> Optional[str]:
        """
        Отвечает на комментарий
        """
        try:
            response = self._make_request(
                'POST',
                f"{ig_comment_id}/replies",
                data={'message': message}
            )
            return response.get('id')
        except InstagramAPIError as e:
            logger.error(f"Failed to reply to comment {ig_comment_id}: {e}")
            return None


class InstagramMessengerService:
    """
    Сервис для работы с Instagram Messaging API
    """
    
    def __init__(self, account: IGAccount):
        self.account = account
        self.access_token = account.get_access_token()
        self.page_id = account.page_id
    
    def _make_request(self, method: str, endpoint: str, data: dict = None, params: dict = None) -> dict:
        """
        Выполняет запрос к Messenger API
        """
        url = f"{GRAPH_API_BASE}/{endpoint}"
        
        # Добавляем access_token к параметрам
        if params is None:
            params = {}
        params['access_token'] = self.access_token
        
        try:
            if method.upper() == 'GET':
                response = requests.get(url, params=params, timeout=API_TIMEOUT)
            else:
                response = requests.post(url, data=data, params=params, timeout=API_TIMEOUT)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Messenger API request failed: {e}")
            raise InstagramAPIError(f"Messenger API request failed: {str(e)}")
    
    def send_message(self, recipient_id: str, message_text: str) -> Optional[str]:
        """
        Отправляет сообщение пользователю
        """
        try:
            response = self._make_request(
                'POST',
                f"{self.page_id}/messages",
                data={
                    'recipient': json.dumps({'id': recipient_id}),
                    'message': json.dumps({'text': message_text})
                }
            )
            return response.get('message_id')
        except InstagramAPIError as e:
            logger.error(f"Failed to send message to {recipient_id}: {e}")
            return None
    
    def get_conversations(self, limit: int = 50) -> List[dict]:
        """
        Получает список диалогов
        """
        try:
            response = self._make_request(
                'GET',
                f"{self.page_id}/conversations",
                params={
                    'fields': 'participants,updated_time,message_count',
                    'limit': limit
                }
            )
            return response.get('data', [])
        except InstagramAPIError as e:
            logger.warning(f"Failed to get conversations: {e}")
            return []
    
    def get_messages(self, conversation_id: str, limit: int = 100) -> List[dict]:
        """
        Получает сообщения из диалога
        """
        try:
            response = self._make_request(
                'GET',
                f"{conversation_id}/messages",
                params={
                    'fields': 'id,created_time,from,to,message,attachments',
                    'limit': limit
                }
            )
            return response.get('data', [])
        except InstagramAPIError as e:
            logger.warning(f"Failed to get messages for conversation {conversation_id}: {e}")
            return []


class InstagramTokenService:
    """
    Сервис для работы с токенами доступа
    """
    
    @staticmethod
    def exchange_short_for_long_lived_token(short_lived_token: str) -> Tuple[str, datetime]:
        """
        Обменивает краткосрочный токен на долгосрочный (60 дней)
        """
        try:
            response = requests.get(
                f"{GRAPH_API_BASE}/oauth/access_token",
                params={
                    'grant_type': 'fb_exchange_token',
                    'client_id': settings.META_APP_ID,
                    'client_secret': settings.META_APP_SECRET,
                    'fb_exchange_token': short_lived_token
                },
                timeout=API_TIMEOUT
            )
            
            response.raise_for_status()
            data = response.json()
            
            long_lived_token = data['access_token']
            expires_in = data.get('expires_in', 5184000)  # 60 дней по умолчанию
            expires_at = timezone.now() + timedelta(seconds=expires_in)
            
            return long_lived_token, expires_at
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Token exchange failed: {e}")
            raise InstagramAPIError(f"Token exchange failed: {str(e)}")
    
    @staticmethod
    def refresh_long_lived_token(current_token: str) -> Tuple[str, datetime]:
        """
        Обновляет долгосрочный токен
        """
        try:
            response = requests.get(
                f"{GRAPH_API_BASE}/oauth/access_token",
                params={
                    'grant_type': 'fb_exchange_token',
                    'client_id': settings.META_APP_ID,
                    'client_secret': settings.META_APP_SECRET,
                    'fb_exchange_token': current_token
                },
                timeout=API_TIMEOUT
            )
            
            response.raise_for_status()
            data = response.json()
            
            new_token = data['access_token']
            expires_in = data.get('expires_in', 5184000)  # 60 дней по умолчанию
            expires_at = timezone.now() + timedelta(seconds=expires_in)
            
            return new_token, expires_at
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Token refresh failed: {e}")
            raise InstagramAPIError(f"Token refresh failed: {str(e)}")
    
    @staticmethod
    def get_user_pages_and_instagram_accounts(access_token: str) -> List[dict]:
        """
        Получает список страниц пользователя и связанных Instagram аккаунтов
        """
        try:
            # Получаем страницы пользователя
            response = requests.get(
                f"{GRAPH_API_BASE}/me/accounts",
                params={
                    'access_token': access_token,
                    'fields': 'id,name,access_token'
                },
                timeout=API_TIMEOUT
            )
            
            response.raise_for_status()
            pages_data = response.json()
            
            instagram_accounts = []
            
            # Для каждой страницы проверяем связанный Instagram аккаунт
            for page in pages_data.get('data', []):
                page_id = page['id']
                page_access_token = page['access_token']
                
                try:
                    ig_response = requests.get(
                        f"{GRAPH_API_BASE}/{page_id}",
                        params={
                            'access_token': page_access_token,
                            'fields': 'instagram_business_account'
                        },
                        timeout=API_TIMEOUT
                    )
                    
                    ig_response.raise_for_status()
                    ig_data = ig_response.json()
                    
                    if 'instagram_business_account' in ig_data:
                        ig_account_id = ig_data['instagram_business_account']['id']
                        
                        # Получаем информацию об Instagram аккаунте
                        ig_info_response = requests.get(
                            f"{GRAPH_API_BASE}/{ig_account_id}",
                            params={
                                'access_token': page_access_token,
                                'fields': 'id,username,profile_picture_url,followers_count'
                            },
                            timeout=API_TIMEOUT
                        )
                        
                        ig_info_response.raise_for_status()
                        ig_info = ig_info_response.json()
                        
                        instagram_accounts.append({
                            'page_id': page_id,
                            'page_name': page['name'],
                            'page_access_token': page_access_token,
                            'ig_user_id': ig_account_id,
                            'ig_username': ig_info.get('username'),
                            'ig_profile_picture': ig_info.get('profile_picture_url'),
                            'ig_followers_count': ig_info.get('followers_count', 0)
                        })
                        
                except requests.exceptions.RequestException:
                    # Страница не связана с Instagram Business аккаунтом
                    continue
            
            return instagram_accounts
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get user pages and Instagram accounts: {e}")
            raise InstagramAPIError(f"Failed to get user pages and Instagram accounts: {str(e)}")


def create_utm_link(base_url: str, utm_params: dict) -> str:
    """
    Создает ссылку с UTM параметрами
    """
    from urllib.parse import urlencode
    
    # Фильтруем пустые значения
    clean_params = {k: v for k, v in utm_params.items() if v}
    
    if not clean_params:
        return base_url
    
    utm_string = urlencode(clean_params)
    separator = '&' if '?' in base_url else '?'
    
    return f"{base_url}{separator}{utm_string}"


def is_within_24h_window(last_user_message_time: datetime) -> bool:
    """
    Проверяет, находится ли диалог в 24-часовом окне для промо-контента
    """
    return timezone.now() - last_user_message_time <= timedelta(hours=24)


def sanitize_dm_text(text: str) -> str:
    """
    Очищает текст DM сообщения от чувствительной информации
    """
    import re
    
    # Маскируем телефоны
    text = re.sub(r'\b\+?[\d\s\-\(\)]{7,}\b', '[phone]', text)
    
    # Маскируем email
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', '[email]', text)
    
    return text
