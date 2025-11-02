"""
Google Wallet API Client
Интеграция с Google Wallet Objects API для создания и управления карточками
"""

import base64
import json
import time
import requests
import jwt
from typing import Dict, Any, Optional, List
from django.conf import settings
from django.utils import timezone
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession


# Google Wallet API endpoints
SCOPES = ["https://www.googleapis.com/auth/wallet_object.issuer"]
API_BASE = "https://walletobjects.googleapis.com/walletobjects/v1"


class GoogleWalletError(Exception):
    """Исключение для ошибок Google Wallet API"""
    pass


def _get_auth_session() -> AuthorizedSession:
    """Создает авторизованную сессию для Google Wallet API"""
    try:
        # Декодируем ключ сервис-аккаунта из настроек
        key_data = base64.b64decode(settings.GOOGLE_WALLET_SA_KEY_JSON_BASE64)
        key_info = json.loads(key_data)
        
        # Создаем учетные данные
        credentials = service_account.Credentials.from_service_account_info(
            key_info, scopes=SCOPES
        )
        
        # Возвращаем авторизованную сессию
        return AuthorizedSession(credentials)
    except Exception as e:
        raise GoogleWalletError(f"Failed to create auth session: {e}")


def ensure_offer_class(business) -> Dict[str, Any]:
    """
    Создает или обновляет класс предложений в Google Wallet
    
    Args:
        business: Бизнес объект
        
    Returns:
        Dict с данными созданного/существующего класса
    """
    session = _get_auth_session()
    class_id = f"{settings.GOOGLE_WALLET_ISSUER_ID}.{business.slug}_offers"
    
    # Проверяем существование класса
    try:
        response = session.get(f"{API_BASE}/offerClass/{class_id}")
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    
    # Создаем новый класс
    locations = []
    if hasattr(business, 'locations') and business.locations.exists():
        for location in business.locations.all():
            if location.latitude and location.longitude:
                locations.append({
                    "latitude": float(location.latitude),
                    "longitude": float(location.longitude),
                    "name": location.name
                })
    
    # Если нет локаций в БД, используем дефолтные
    if not locations:
        locations = [
            {"latitude": 43.238949, "longitude": 76.889709, "name": f"{business.name} - Main"}
        ]
    
    class_payload = {
        "id": class_id,
        "issuerName": business.name,
        "title": f"Скидочная карта {business.name}",
        "provider": business.name,
        "hexBackgroundColor": getattr(business, 'brand_color', '#111827'),
        "reviewStatus": "UNDER_REVIEW",
        "redemptionIssuers": [settings.GOOGLE_WALLET_ISSUER_ID],
        "locations": locations,
        "titleImage": {
            "sourceUri": {
                "uri": getattr(business, 'logo_url', 'https://via.placeholder.com/300x100/111827/ffffff?text=Logo')
            }
        }
    }
    
    try:
        response = session.post(f"{API_BASE}/offerClass", json=class_payload)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise GoogleWalletError(f"Failed to create offer class: {e}")


def build_offer_object(wallet_pass) -> Dict[str, Any]:
    """
    Строит объект предложения для Google Wallet
    
    Args:
        wallet_pass: Объект WalletPass
        
    Returns:
        Dict с данными объекта для Google Wallet
    """
    # Формируем базовый объект
    offer_object = {
        "id": wallet_pass.object_id,
        "classId": wallet_pass.class_id,
        "state": "active" if wallet_pass.status == 'active' else "inactive",
        
        # Штрих-код
        "barcode": {
            "type": "qrCode",
            "value": wallet_pass.barcode_value,
            "alternateText": wallet_pass.barcode_value
        },
        
        # Заголовки
        "title": wallet_pass.title,
        "subtitle": wallet_pass.subtitle or "Покажите при оплате",
        
        # Сроки действия
        "validTimeInterval": {},
        
        # Текстовые модули
        "textModulesData": []
    }
    
    # Добавляем срок действия
    if wallet_pass.valid_from:
        offer_object["validTimeInterval"]["start"] = {
            "date": wallet_pass.valid_from.isoformat()
        }
    
    if wallet_pass.valid_until:
        offer_object["validTimeInterval"]["end"] = {
            "date": wallet_pass.valid_until.isoformat()
        }
    
    # Добавляем информацию о купоне
    if wallet_pass.coupon:
        coupon = wallet_pass.coupon
        campaign = coupon.campaign
        
        text_modules = [
            {
                "header": "Кампания",
                "body": campaign.name
            }
        ]
        
        if campaign.description:
            text_modules.append({
                "header": "Условия",
                "body": campaign.description[:100]
            })
        
        if coupon.expires_at:
            text_modules.append({
                "header": "Действует до",
                "body": coupon.expires_at.strftime("%d.%m.%Y %H:%M")
            })
        
        offer_object["textModulesData"] = text_modules
    
    # Добавляем локации если есть
    if wallet_pass.business.locations.exists():
        locations = []
        for location in wallet_pass.business.locations.all():
            if location.geo_lat and location.geo_lng:
                locations.append({
                    "latitude": float(location.geo_lat),
                    "longitude": float(location.geo_lng)
                })
        
        if locations:
            offer_object["locations"] = locations
    
    return offer_object


def create_save_link(offer_object: Dict[str, Any]) -> str:
    """
    Создает JWT ссылку "Save to Google Wallet"
    
    Args:
        offer_object: Объект предложения
        
    Returns:
        URL для сохранения в Google Wallet
    """
    try:
        # Получаем данные сервис-аккаунта
        key_data = base64.b64decode(settings.GOOGLE_WALLET_SA_KEY_JSON_BASE64)
        key_info = json.loads(key_data)
        
        private_key = key_info["private_key"]
        service_account_email = key_info["client_email"]
        
        # Создаем JWT claims
        now = int(time.time())
        claims = {
            "iss": service_account_email,
            "aud": "google",
            "typ": "savetowallet",
            "iat": now,
            "exp": now + 3600,  # Действует 1 час
            "payload": {
                "offerObjects": [offer_object]
            }
        }
        
        # Подписываем JWT
        token = jwt.encode(claims, private_key, algorithm="RS256")
        
        # Возвращаем ссылку
        return f"https://pay.google.com/gp/v/save/{token}"
        
    except Exception as e:
        raise GoogleWalletError(f"Failed to create save link: {e}")


def update_offer_object(object_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Обновляет существующий объект в Google Wallet
    
    Args:
        object_id: ID объекта
        updates: Словарь с обновлениями
        
    Returns:
        Обновленный объект
    """
    session = _get_auth_session()
    
    try:
        response = session.patch(f"{API_BASE}/offerObject/{object_id}", json=updates)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise GoogleWalletError(f"Failed to update offer object: {e}")


def send_expiry_notification(wallet_pass, message: str = None):
    """
    Отправляет уведомление об истечении срока действия
    
    Args:
        wallet_pass: Объект WalletPass
        message: Пользовательское сообщение
    """
    if not message:
        if wallet_pass.valid_until:
            days_left = (wallet_pass.valid_until - timezone.now()).days
            if days_left <= 1:
                message = "Ваша скидка истекает сегодня!"
            else:
                message = f"Ваша скидка истекает через {days_left} дн."
        else:
            message = "Не забудьте воспользоваться скидкой!"
    
    # Обновляем объект с новым сообщением
    updates = {
        "textModulesData": [
            {
                "header": "⏰ Напоминание",
                "body": message
            }
        ]
    }
    
    try:
        update_offer_object(wallet_pass.object_id, updates)
        return True
    except GoogleWalletError as e:
        print(f"Failed to send expiry notification: {e}")
        return False


def update_wallet_object(object_id: str, update_data: Dict[str, Any]) -> bool:
    """
    Обновляет объект в Google Wallet (для Streaks, Power Hour, etc.)
    
    Args:
        object_id: ID объекта для обновления
        update_data: Данные для обновления
        
    Returns:
        True если успешно, False если ошибка
    """
    session = _get_auth_session()
    
    try:
        response = session.patch(f"{API_BASE}/offerObject/{object_id}", json=update_data)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Failed to update wallet object {object_id}: {e}")
        return False


def get_object_status(object_id: str) -> Optional[Dict[str, Any]]:
    """
    Получает статус объекта из Google Wallet
    
    Args:
        object_id: ID объекта
        
    Returns:
        Данные объекта или None если не найден
    """
    session = _get_auth_session()
    
    try:
        response = session.get(f"{API_BASE}/offerObject/{object_id}")
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None
