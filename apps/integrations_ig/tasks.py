"""
Celery задачи для Instagram интеграции
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

try:
    from celery import shared_task
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    # Fallback декоратор для разработки без Celery
    def shared_task(func):
        return func

from django.utils import timezone
from django.db import transaction
from django.conf import settings

from .models import (
    IGAccount, IGMedia, IGComment, IGThreadMessage, 
    IGWebhookEvent, IGDMTemplate, IGMediaStatus, IGAccountStatus
)
from .services import (
    InstagramAPIService, InstagramMessengerService, InstagramTokenService,
    InstagramAPIError, is_within_24h_window, sanitize_dm_text
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def sync_account_info(self, account_id: int):
    """
    Синхронизирует информацию об Instagram аккаунте
    """
    try:
        account = IGAccount.objects.get(id=account_id)
        api = InstagramAPIService(account)
        
        # Получаем актуальную информацию
        account_info = api.get_account_info()
        
        # Обновляем данные
        account.username = account_info.get('username', account.username)
        account.followers_count = account_info.get('followers_count', account.followers_count)
        account.profile_picture_url = account_info.get('profile_picture_url', account.profile_picture_url)
        account.last_sync_at = timezone.now()
        account.status = IGAccountStatus.CONNECTED
        account.save()
        
        logger.info(f'Successfully synced Instagram account {account.username}')
        
    except IGAccount.DoesNotExist:
        logger.error(f'Instagram account {account_id} not found')
    except InstagramAPIError as e:
        logger.error(f'Failed to sync Instagram account {account_id}: {e}')
        self.retry(countdown=60 * (self.request.retries + 1))
    except Exception as e:
        logger.error(f'Unexpected error syncing Instagram account {account_id}: {e}')
        self.retry(countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=3)
def publish_media_task(self, media_id: int):
    """
    Публикует медиа в Instagram
    """
    try:
        media = IGMedia.objects.get(id=media_id)
        account = media.account
        api = InstagramAPIService(account)
        
        # Создаем контейнер для медиа
        if media.media_type == 'carousel' and media.children_data:
            # Для карусели создаем контейнеры для каждого элемента
            children_ids = []
            for child_data in media.children_data:
                child_id = api.create_media_container(
                    media_type=child_data['type'],
                    media_url=child_data['url']
                )
                children_ids.append(child_id)
            
            # Создаем контейнер карусели
            creation_id = api.create_media_container(
                media_type='carousel',
                caption=media.caption,
                children=children_ids
            )
        else:
            # Обычный пост или reel
            creation_id = api.create_media_container(
                media_type=media.media_type,
                media_url=media.media_url,
                caption=media.caption,
                is_reel=(media.media_type == 'reel')
            )
        
        # Сохраняем creation_id
        media.creation_id = creation_id
        media.save(update_fields=['creation_id'])
        
        # Публикуем
        ig_media_id = api.publish_media(creation_id)
        
        # Получаем информацию о опубликованном медиа
        media_info = api.get_media_info(ig_media_id)
        
        # Обновляем модель
        with transaction.atomic():
            media.ig_media_id = ig_media_id
            media.permalink = media_info.get('permalink', '')
            media.status = IGMediaStatus.PUBLISHED
            media.published_at = timezone.now()
            media.save()
        
        logger.info(f'Successfully published media {media_id} to Instagram as {ig_media_id}')
        
        # Запускаем синхронизацию метрик через некоторое время
        sync_media_insights.apply_async(args=[media.id], countdown=300)  # 5 минут
        
    except IGMedia.DoesNotExist:
        logger.error(f'Media {media_id} not found')
    except InstagramAPIError as e:
        logger.error(f'Failed to publish media {media_id}: {e}')
        
        # Обновляем статус на failed
        try:
            media = IGMedia.objects.get(id=media_id)
            media.status = IGMediaStatus.FAILED
            media.error_message = str(e)
            media.save()
        except IGMedia.DoesNotExist:
            pass
        
        self.retry(countdown=60 * (self.request.retries + 1))
    except Exception as e:
        logger.error(f'Unexpected error publishing media {media_id}: {e}')
        self.retry(countdown=60 * (self.request.retries + 1))


@shared_task
def publish_scheduled_media():
    """
    Публикует медиа, которое запланировано на текущее время
    """
    now = timezone.now()
    
    # Находим медиа, которое пора публиковать
    due_media = IGMedia.objects.filter(
        status=IGMediaStatus.SCHEDULED,
        publish_at__lte=now
    ).select_related('account')
    
    count = 0
    for media in due_media:
        try:
            publish_media_task.delay(media.id)
            count += 1
        except Exception as e:
            logger.error(f'Failed to queue media {media.id} for publishing: {e}')
    
    if count > 0:
        logger.info(f'Queued {count} scheduled media for publishing')
    
    return count


@shared_task(bind=True, max_retries=2)
def sync_media_insights(self, media_id: int):
    """
    Синхронизирует метрики медиа из Instagram Insights
    """
    try:
        media = IGMedia.objects.get(id=media_id)
        
        if not media.ig_media_id or media.status != IGMediaStatus.PUBLISHED:
            logger.warning(f'Media {media_id} is not published, skipping insights sync')
            return
        
        account = media.account
        api = InstagramAPIService(account)
        
        # Получаем метрики
        insights = api.get_media_insights(media.ig_media_id, media.media_type)
        
        if insights:
            # Обновляем метрики
            media.reach = insights.get('reach', media.reach)
            media.impressions = insights.get('impressions', media.impressions)
            media.likes = insights.get('likes', media.likes)
            media.comments_count = insights.get('comments', media.comments_count)
            media.saves = insights.get('saves', media.saves)
            media.shares = insights.get('shares', media.shares)
            media.plays = insights.get('plays', media.plays)
            media.last_insights_sync = timezone.now()
            media.save()
            
            logger.info(f'Successfully synced insights for media {media_id}')
        
    except IGMedia.DoesNotExist:
        logger.error(f'Media {media_id} not found')
    except InstagramAPIError as e:
        logger.warning(f'Failed to sync insights for media {media_id}: {e}')
        # Не ретраим для insights - это не критично
    except Exception as e:
        logger.error(f'Unexpected error syncing insights for media {media_id}: {e}')
        self.retry(countdown=60 * (self.request.retries + 1))


@shared_task
def sync_all_media_insights():
    """
    Синхронизирует метрики для всех опубликованных медиа
    """
    # Синхронизируем медиа, которое не обновлялось последние 6 часов
    cutoff_time = timezone.now() - timedelta(hours=6)
    
    media_to_sync = IGMedia.objects.filter(
        status=IGMediaStatus.PUBLISHED,
        ig_media_id__isnull=False
    ).filter(
        models.Q(last_insights_sync__isnull=True) |
        models.Q(last_insights_sync__lt=cutoff_time)
    )[:100]  # Ограничиваем количество для избежания rate limits
    
    count = 0
    for media in media_to_sync:
        try:
            sync_media_insights.delay(media.id)
            count += 1
        except Exception as e:
            logger.error(f'Failed to queue insights sync for media {media.id}: {e}')
    
    if count > 0:
        logger.info(f'Queued {count} media for insights sync')
    
    return count


@shared_task(bind=True, max_retries=3)
def sync_media_comments(self, media_id: int):
    """
    Синхронизирует комментарии к медиа
    """
    try:
        media = IGMedia.objects.get(id=media_id)
        
        if not media.ig_media_id:
            logger.warning(f'Media {media_id} has no ig_media_id, skipping comments sync')
            return
        
        account = media.account
        api = InstagramAPIService(account)
        
        # Получаем комментарии
        comments_data = api.get_media_comments(media.ig_media_id)
        
        synced_count = 0
        for comment_data in comments_data:
            comment_id = comment_data['id']
            
            # Проверяем, есть ли уже такой комментарий
            if IGComment.objects.filter(ig_comment_id=comment_id).exists():
                continue
            
            # Создаем новый комментарий
            comment = IGComment.objects.create(
                media=media,
                ig_comment_id=comment_id,
                ig_parent_id=comment_data.get('parent_id', ''),
                text=comment_data.get('text', ''),
                author_username=comment_data.get('username', ''),
                created_at=datetime.fromisoformat(comment_data['timestamp'].replace('Z', '+00:00'))
            )
            
            synced_count += 1
            
            # Запускаем AI анализ комментария
            from apps.reviews.tasks import analyze_review_task
            try:
                analyze_review_task.delay(comment.id, model_type='ig_comment')
            except Exception as e:
                logger.warning(f'Failed to queue AI analysis for comment {comment.id}: {e}')
        
        logger.info(f'Synced {synced_count} new comments for media {media_id}')
        
    except IGMedia.DoesNotExist:
        logger.error(f'Media {media_id} not found')
    except InstagramAPIError as e:
        logger.error(f'Failed to sync comments for media {media_id}: {e}')
        self.retry(countdown=60 * (self.request.retries + 1))
    except Exception as e:
        logger.error(f'Unexpected error syncing comments for media {media_id}: {e}')
        self.retry(countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=3)
def process_webhook_event(self, event_id: int):
    """
    Обрабатывает событие от Instagram webhook
    """
    try:
        event = IGWebhookEvent.objects.get(id=event_id)
        
        if event.processed:
            logger.info(f'Webhook event {event_id} already processed')
            return
        
        payload = event.raw_payload
        
        if event.kind == 'comment':
            # Обрабатываем новый комментарий
            comment_data = payload.get('value', {})
            media_id = comment_data.get('media_id')
            
            if media_id:
                try:
                    media = IGMedia.objects.get(ig_media_id=media_id)
                    sync_media_comments.delay(media.id)
                except IGMedia.DoesNotExist:
                    logger.warning(f'Media {media_id} not found for comment webhook')
        
        elif event.kind == 'message':
            # Обрабатываем новое сообщение
            message_data = payload.get('value', {})
            process_dm_message.delay(message_data)
        
        # Помечаем событие как обработанное
        event.processed = True
        event.processed_at = timezone.now()
        event.save()
        
        logger.info(f'Successfully processed webhook event {event_id}')
        
    except IGWebhookEvent.DoesNotExist:
        logger.error(f'Webhook event {event_id} not found')
    except Exception as e:
        logger.error(f'Error processing webhook event {event_id}: {e}')
        
        # Увеличиваем счетчик ретраев
        try:
            event = IGWebhookEvent.objects.get(id=event_id)
            event.retry_count += 1
            event.error_message = str(e)
            event.save()
        except IGWebhookEvent.DoesNotExist:
            pass
        
        self.retry(countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=2)
def process_dm_message(self, message_data: dict):
    """
    Обрабатывает входящее DM сообщение
    """
    try:
        sender_id = message_data.get('from', {}).get('id')
        recipient_id = message_data.get('to', {}).get('id')
        message_text = message_data.get('message', {}).get('text', '')
        message_id = message_data.get('id')
        timestamp = message_data.get('timestamp')
        
        if not all([sender_id, recipient_id, message_id]):
            logger.warning('Incomplete DM message data')
            return
        
        # Находим аккаунт получателя
        try:
            account = IGAccount.objects.get(ig_user_id=recipient_id)
        except IGAccount.DoesNotExist:
            logger.warning(f'Instagram account {recipient_id} not found')
            return
        
        # Сохраняем сообщение
        thread_id = f"{min(sender_id, recipient_id)}_{max(sender_id, recipient_id)}"
        
        # Проверяем 24-часовое окно
        last_user_message = IGThreadMessage.objects.filter(
            account=account,
            thread_id=thread_id,
            direction='in'
        ).first()
        
        within_24h = True
        if last_user_message:
            within_24h = is_within_24h_window(last_user_message.timestamp)
        
        message = IGThreadMessage.objects.create(
            account=account,
            thread_id=thread_id,
            message_id=message_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            text=sanitize_dm_text(message_text),
            direction='in',
            is_within_24h_window=within_24h,
            timestamp=datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        )
        
        # Проверяем автоответы
        if account.dm_bot_enabled and within_24h:
            check_dm_autoresponse.delay(message.id)
        
        logger.info(f'Processed DM message {message_id} for account {account.username}')
        
    except Exception as e:
        logger.error(f'Error processing DM message: {e}')
        self.retry(countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=2)
def check_dm_autoresponse(self, message_id: int):
    """
    Проверяет и отправляет автоответ на DM сообщение
    """
    try:
        message = IGThreadMessage.objects.get(id=message_id)
        account = message.account
        
        if not message.text or message.direction != 'in':
            return
        
        # Ищем подходящий шаблон
        templates = IGDMTemplate.objects.filter(
            account=account,
            enabled=True
        ).order_by('priority')
        
        matching_template = None
        for template in templates:
            if template.matches_message(message.text):
                matching_template = template
                break
        
        if not matching_template:
            logger.info(f'No matching template found for message {message_id}')
            return
        
        # Подготавливаем ответ
        response_text = matching_template.response_text
        
        # Если нужен купон
        if matching_template.include_coupon and matching_template.coupon_campaign:
            from apps.coupons.services import issue_coupon
            try:
                # Создаем персональный купон
                coupon = issue_coupon(
                    matching_template.coupon_campaign,
                    phone=f"ig_{message.sender_id}",  # Используем IG ID как телефон
                    expires_at=matching_template.coupon_campaign.ends_at
                )
                
                # Добавляем ссылку на купон в ответ
                coupon_url = f"https://example.com/c/{coupon.code}"  # TODO: правильный URL
                response_text += f"\n\n🎟️ Ваш купон: {coupon_url}"
                
            except Exception as e:
                logger.error(f'Failed to create coupon for DM template {matching_template.id}: {e}')
        
        # Отправляем ответ
        messenger = InstagramMessengerService(account)
        sent_message_id = messenger.send_message(message.sender_id, response_text)
        
        if sent_message_id:
            # Сохраняем отправленное сообщение
            IGThreadMessage.objects.create(
                account=account,
                thread_id=message.thread_id,
                message_id=sent_message_id,
                sender_id=account.ig_user_id,
                recipient_id=message.sender_id,
                text=response_text,
                direction='out',
                is_bot_response=True,
                is_within_24h_window=True,
                timestamp=timezone.now()
            )
            
            # Увеличиваем счетчик использования шаблона
            matching_template.usage_count += 1
            matching_template.save(update_fields=['usage_count'])
            
            logger.info(f'Sent autoresponse for message {message_id} using template {matching_template.id}')
        
    except IGThreadMessage.DoesNotExist:
        logger.error(f'DM message {message_id} not found')
    except Exception as e:
        logger.error(f'Error sending autoresponse for message {message_id}: {e}')
        self.retry(countdown=60 * (self.request.retries + 1))


@shared_task
def refresh_expiring_tokens():
    """
    Обновляет токены, которые скоро истекут
    """
    # Находим аккаунты с токенами, которые истекают в течение 7 дней
    expiring_accounts = IGAccount.objects.filter(
        status=IGAccountStatus.CONNECTED,
        token_expires_at__lte=timezone.now() + timedelta(days=7)
    )
    
    refreshed_count = 0
    for account in expiring_accounts:
        try:
            current_token = account.get_access_token()
            new_token, new_expires_at = InstagramTokenService.refresh_long_lived_token(current_token)
            
            account.set_access_token(new_token)
            account.token_expires_at = new_expires_at
            account.status = IGAccountStatus.CONNECTED
            account.save()
            
            refreshed_count += 1
            logger.info(f'Refreshed token for Instagram account {account.username}')
            
        except InstagramAPIError as e:
            logger.error(f'Failed to refresh token for account {account.id}: {e}')
            account.status = IGAccountStatus.EXPIRED
            account.save()
        except Exception as e:
            logger.error(f'Unexpected error refreshing token for account {account.id}: {e}')
    
    if refreshed_count > 0:
        logger.info(f'Refreshed tokens for {refreshed_count} Instagram accounts')
    
    return refreshed_count


# Добавляем импорт models для Q объектов
from django.db import models
