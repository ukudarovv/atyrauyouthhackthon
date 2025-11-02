"""
Views для Instagram интеграции
"""
import json
import logging
from datetime import datetime
from urllib.parse import urlencode, parse_qs, urlparse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST
from django.conf import settings
from django.utils import timezone
from django.core.paginator import Paginator
from django.db import transaction

from apps.businesses.models import Business
from .models import (
    IGAccount, IGMedia, IGComment, IGThreadMessage, 
    IGWebhookEvent, IGDMTemplate, IGMediaStatus, IGMediaType
)
from .services import (
    InstagramAPIService, InstagramMessengerService, InstagramTokenService,
    InstagramAPIError, create_utm_link
)

logger = logging.getLogger(__name__)


def _get_current_business(request):
    """Получает текущий бизнес пользователя"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        return None
    
    if request.user.is_superuser:
        return Business.objects.filter(id=biz_id).first()
    else:
        return Business.objects.filter(id=biz_id, owner=request.user).first()


@login_required
def connect_instagram(request):
    """
    Начало OAuth флоу для подключения Instagram
    """
    business = _get_current_business(request)
    if not business:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    # Проверяем, не подключен ли уже Instagram
    if hasattr(business, 'ig_account'):
        messages.info(request, 'Instagram уже подключен к этому бизнесу.')
        return redirect('integrations_ig:dashboard')
    
    # Формируем URL для Facebook Login
    facebook_auth_url = 'https://www.facebook.com/v20.0/dialog/oauth'
    
    # Необходимые разрешения для Instagram Business API
    scope = [
        'instagram_basic',
        'pages_show_list', 
        'instagram_content_publish',
        'instagram_manage_comments',
        'instagram_manage_messages',
        'pages_messaging'
    ]
    
    auth_params = {
        'client_id': settings.META_APP_ID,
        'redirect_uri': settings.META_REDIRECT_URI,
        'scope': ','.join(scope),
        'response_type': 'code',
        'state': str(business.id)  # передаем ID бизнеса для безопасности
    }
    
    auth_url = f"{facebook_auth_url}?{urlencode(auth_params)}"
    
    context = {
        'business': business,
        'auth_url': auth_url,
        'required_permissions': scope
    }
    
    return render(request, 'integrations_ig/connect.html', context)


@login_required
def oauth_callback(request):
    """
    Обработка callback от Facebook OAuth
    """
    code = request.GET.get('code')
    state = request.GET.get('state')
    error = request.GET.get('error')
    
    if error:
        messages.error(request, f'Ошибка авторизации Facebook: {error}')
        return redirect('integrations_ig:connect')
    
    if not code or not state:
        messages.error(request, 'Неверные параметры авторизации.')
        return redirect('integrations_ig:connect')
    
    # Проверяем state (ID бизнеса)
    try:
        business_id = int(state)
        business = get_object_or_404(Business, id=business_id, owner=request.user)
    except (ValueError, Business.DoesNotExist):
        messages.error(request, 'Неверный state параметр.')
        return redirect('integrations_ig:connect')
    
    try:
        # Обмениваем code на access_token
        token_response = InstagramTokenService._make_token_request(
            'https://graph.facebook.com/v20.0/oauth/access_token',
            {
                'client_id': settings.META_APP_ID,
                'client_secret': settings.META_APP_SECRET,
                'redirect_uri': settings.META_REDIRECT_URI,
                'code': code
            }
        )
        
        short_lived_token = token_response['access_token']
        
        # Обмениваем на долгосрочный токен
        long_lived_token, expires_at = InstagramTokenService.exchange_short_for_long_lived_token(
            short_lived_token
        )
        
        # Получаем Instagram аккаунты пользователя
        instagram_accounts = InstagramTokenService.get_user_pages_and_instagram_accounts(
            long_lived_token
        )
        
        if not instagram_accounts:
            messages.error(request, 
                'Не найдено Instagram Business аккаунтов. '
                'Убедитесь, что у вас есть Instagram Business профиль, '
                'связанный с Facebook страницей.'
            )
            return redirect('integrations_ig:connect')
        
        # Если найдено несколько аккаунтов, показываем выбор
        if len(instagram_accounts) > 1:
            request.session['instagram_accounts'] = instagram_accounts
            request.session['long_lived_token'] = long_lived_token
            request.session['token_expires_at'] = expires_at.isoformat()
            return redirect('integrations_ig:select_account')
        
        # Если один аккаунт - создаем сразу
        ig_data = instagram_accounts[0]
        
        with transaction.atomic():
            ig_account = IGAccount.objects.create(
                business=business,
                ig_user_id=ig_data['ig_user_id'],
                page_id=ig_data['page_id'],
                username=ig_data['ig_username'],
                profile_picture_url=ig_data.get('ig_profile_picture', ''),
                followers_count=ig_data.get('ig_followers_count', 0),
                token_expires_at=expires_at,
                permissions=['instagram_basic', 'instagram_content_publish', 'instagram_manage_comments']
            )
            
            ig_account.set_access_token(ig_data['page_access_token'])
            ig_account.save()
        
        messages.success(request, 
            f'Instagram аккаунт @{ig_data["ig_username"]} успешно подключен!'
        )
        
        # Запускаем начальную синхронизацию
        from .tasks import sync_account_info
        try:
            sync_account_info.delay(ig_account.id)
        except Exception as e:
            logger.warning(f'Failed to start sync task: {e}')
        
        return redirect('integrations_ig:dashboard')
        
    except InstagramAPIError as e:
        logger.error(f'Instagram OAuth error: {e}')
        messages.error(request, f'Ошибка подключения Instagram: {str(e)}')
        return redirect('integrations_ig:connect')
    except Exception as e:
        logger.error(f'Unexpected OAuth error: {e}')
        messages.error(request, 'Произошла неожиданная ошибка. Попробуйте еще раз.')
        return redirect('integrations_ig:connect')


@login_required
def select_account(request):
    """
    Выбор Instagram аккаунта (если найдено несколько)
    """
    instagram_accounts = request.session.get('instagram_accounts')
    if not instagram_accounts:
        messages.error(request, 'Сессия истекла. Попробуйте подключить заново.')
        return redirect('integrations_ig:connect')
    
    if request.method == 'POST':
        selected_index = request.POST.get('account_index')
        
        try:
            selected_index = int(selected_index)
            ig_data = instagram_accounts[selected_index]
        except (ValueError, IndexError):
            messages.error(request, 'Неверный выбор аккаунта.')
            return redirect('integrations_ig:select_account')
        
        business = _get_current_business(request)
        if not business:
            messages.error(request, 'Бизнес не найден.')
            return redirect('businesses:list')
        
        try:
            long_lived_token = request.session.get('long_lived_token')
            expires_at = datetime.fromisoformat(request.session.get('token_expires_at'))
            
            with transaction.atomic():
                ig_account = IGAccount.objects.create(
                    business=business,
                    ig_user_id=ig_data['ig_user_id'],
                    page_id=ig_data['page_id'],
                    username=ig_data['ig_username'],
                    profile_picture_url=ig_data.get('ig_profile_picture', ''),
                    followers_count=ig_data.get('ig_followers_count', 0),
                    token_expires_at=expires_at,
                    permissions=['instagram_basic', 'instagram_content_publish', 'instagram_manage_comments']
                )
                
                ig_account.set_access_token(ig_data['page_access_token'])
                ig_account.save()
            
            # Очищаем сессию
            for key in ['instagram_accounts', 'long_lived_token', 'token_expires_at']:
                request.session.pop(key, None)
            
            messages.success(request, 
                f'Instagram аккаунт @{ig_data["ig_username"]} успешно подключен!'
            )
            
            return redirect('integrations_ig:dashboard')
            
        except Exception as e:
            logger.error(f'Error creating Instagram account: {e}')
            messages.error(request, 'Ошибка при создании аккаунта.')
            return redirect('integrations_ig:connect')
    
    context = {
        'instagram_accounts': instagram_accounts
    }
    
    return render(request, 'integrations_ig/select_account.html', context)


@login_required
def dashboard(request):
    """
    Главная страница Instagram интеграции
    """
    business = _get_current_business(request)
    if not business:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    try:
        ig_account = business.ig_account
    except IGAccount.DoesNotExist:
        messages.info(request, 'Instagram не подключен к этому бизнесу.')
        return redirect('integrations_ig:connect')
    
    # Статистика медиа
    media_stats = {
        'total': ig_account.media.count(),
        'published': ig_account.media.filter(status=IGMediaStatus.PUBLISHED).count(),
        'scheduled': ig_account.media.filter(status=IGMediaStatus.SCHEDULED).count(),
        'drafts': ig_account.media.filter(status=IGMediaStatus.DRAFT).count(),
    }
    
    # Последние медиа
    recent_media = ig_account.media.all()[:6]
    
    # Статистика комментариев
    comment_stats = {
        'total': IGComment.objects.filter(media__account=ig_account).count(),
        'toxic': IGComment.objects.filter(media__account=ig_account, ai_toxic=True).count(),
        'hidden': IGComment.objects.filter(media__account=ig_account, hidden=True).count(),
    }
    
    # Статистика DM
    dm_stats = {
        'total': ig_account.dm_messages.count(),
        'unread': ig_account.dm_messages.filter(direction='in', is_read=False).count(),
        'bot_responses': ig_account.dm_messages.filter(is_bot_response=True).count(),
    }
    
    context = {
        'business': business,
        'ig_account': ig_account,
        'media_stats': media_stats,
        'recent_media': recent_media,
        'comment_stats': comment_stats,
        'dm_stats': dm_stats,
    }
    
    return render(request, 'integrations_ig/dashboard.html', context)


@login_required
def media_library(request):
    """
    Библиотека медиа контента
    """
    business = _get_current_business(request)
    if not business:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    try:
        ig_account = business.ig_account
    except IGAccount.DoesNotExist:
        messages.error(request, 'Instagram не подключен.')
        return redirect('integrations_ig:connect')
    
    # Фильтры
    media_qs = ig_account.media.all()
    
    status_filter = request.GET.get('status')
    if status_filter:
        media_qs = media_qs.filter(status=status_filter)
    
    media_type_filter = request.GET.get('media_type')
    if media_type_filter:
        media_qs = media_qs.filter(media_type=media_type_filter)
    
    utm_campaign_filter = request.GET.get('utm_campaign')
    if utm_campaign_filter:
        media_qs = media_qs.filter(utm_campaign__icontains=utm_campaign_filter)
    
    # Пагинация
    paginator = Paginator(media_qs, 12)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    context = {
        'business': business,
        'ig_account': ig_account,
        'page_obj': page_obj,
        'current_status': status_filter,
        'current_media_type': media_type_filter,
        'current_utm_campaign': utm_campaign_filter,
        'status_choices': IGMediaStatus.choices,
        'media_type_choices': IGMediaType.choices,
    }
    
    return render(request, 'integrations_ig/media_library.html', context)


@login_required
def media_detail(request, media_id):
    """
    Детальная страница медиа
    """
    business = _get_current_business(request)
    if not business:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    try:
        ig_account = business.ig_account
        media = get_object_or_404(ig_account.media, id=media_id)
    except IGAccount.DoesNotExist:
        messages.error(request, 'Instagram не подключен.')
        return redirect('integrations_ig:connect')
    
    # Комментарии к медиа
    comments = media.comments.all()[:50]
    
    context = {
        'business': business,
        'ig_account': ig_account,
        'media': media,
        'comments': comments,
    }
    
    return render(request, 'integrations_ig/media_detail.html', context)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def webhook_endpoint(request):
    """
    Endpoint для Instagram Webhooks
    """
    if request.method == 'GET':
        # Верификация webhook
        hub_mode = request.GET.get('hub.mode')
        hub_challenge = request.GET.get('hub.challenge')
        hub_verify_token = request.GET.get('hub.verify_token')
        
        if (hub_mode == 'subscribe' and 
            hub_verify_token == settings.META_WEBHOOK_VERIFY_TOKEN):
            logger.info('Instagram webhook verified successfully')
            return HttpResponse(hub_challenge)
        else:
            logger.warning('Instagram webhook verification failed')
            return HttpResponseBadRequest('Verification failed')
    
    elif request.method == 'POST':
        # Обработка webhook событий
        try:
            payload = json.loads(request.body)
            
            # Логируем событие
            logger.info(f'Instagram webhook received: {payload}')
            
            # Обрабатываем каждое событие
            for entry in payload.get('entry', []):
                object_id = entry.get('id')
                
                # Обрабатываем изменения
                for change in entry.get('changes', []):
                    field = change.get('field')
                    value = change.get('value')
                    
                    # Определяем тип события
                    if field == 'comments':
                        event_kind = 'comment'
                    elif field == 'messages':
                        event_kind = 'message'
                    elif field == 'mentions':
                        event_kind = 'mention'
                    else:
                        event_kind = 'unknown'
                    
                    # Сохраняем событие в базу
                    webhook_event = IGWebhookEvent.objects.create(
                        kind=event_kind,
                        raw_payload=change,
                        object_id=value.get('id', object_id) if value else object_id
                    )
                    
                    # Ставим в очередь на обработку
                    from .tasks import process_webhook_event
                    try:
                        process_webhook_event.delay(webhook_event.id)
                    except Exception as e:
                        logger.warning(f'Failed to queue webhook processing: {e}')
            
            return HttpResponse('OK')
            
        except json.JSONDecodeError as e:
            logger.error(f'Invalid webhook payload: {e}')
            return HttpResponseBadRequest('Invalid JSON')
        except Exception as e:
            logger.error(f'Webhook processing error: {e}')
            return HttpResponseBadRequest('Processing error')
    
    return HttpResponseBadRequest('Method not allowed')


@login_required
@require_POST
def publish_media(request, media_id):
    """
    Публикует медиа в Instagram
    """
    business = _get_current_business(request)
    if not business:
        return JsonResponse({'error': 'Бизнес не найден'}, status=400)
    
    try:
        ig_account = business.ig_account
        media = get_object_or_404(ig_account.media, id=media_id)
    except IGAccount.DoesNotExist:
        return JsonResponse({'error': 'Instagram не подключен'}, status=400)
    
    if media.status != IGMediaStatus.DRAFT:
        return JsonResponse({'error': 'Медиа уже опубликовано или в процессе'}, status=400)
    
    # Ставим задачу на публикацию
    from .tasks import publish_media_task
    try:
        publish_media_task.delay(media.id)
        
        # Обновляем статус
        media.status = IGMediaStatus.PUBLISHING
        media.save(update_fields=['status'])
        
        return JsonResponse({
            'success': True,
            'message': 'Медиа поставлено в очередь на публикацию'
        })
        
    except Exception as e:
        logger.error(f'Failed to queue media publishing: {e}')
        return JsonResponse({'error': 'Ошибка постановки в очередь'}, status=500)


# Добавляем вспомогательный метод в InstagramTokenService
InstagramTokenService._make_token_request = lambda url, params: __import__('requests').post(url, params=params, timeout=30).json()
