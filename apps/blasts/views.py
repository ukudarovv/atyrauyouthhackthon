from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse, Http404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
import csv
from io import StringIO

from apps.businesses.models import Business
from apps.segments.models import Segment
from .models import (
    Blast, BlastStatus, BlastTrigger, MessageTemplate, ContactPoint, 
    BlastRecipient, DeliveryAttempt, ShortLink
)
from .services import get_blast_analytics, process_short_link_click
from .tasks import (
    start_blast_task, pause_blast_task, resume_blast_task, 
    cancel_blast_task, sync_contact_points_task, run_sync_fallback
)
from .orchestrator import handle_delivery_webhook
from .webhooks import (
    sendgrid_webhook, twilio_webhook, infobip_webhook, 
    whatsapp_webhook, generic_delivery_webhook
)


@login_required
def blast_list(request):
    """Список рассылок"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    business = get_object_or_404(Business, id=biz_id, owner=request.user)
    
    # Фильтры
    status_filter = request.GET.get('status', '')
    trigger_filter = request.GET.get('trigger', '')
    search = request.GET.get('search', '')
    
    blasts = Blast.objects.filter(business=business).order_by('-created_at')
    
    if status_filter:
        blasts = blasts.filter(status=status_filter)
    
    if trigger_filter:
        blasts = blasts.filter(trigger=trigger_filter)
    
    if search:
        blasts = blasts.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )
    
    # Пагинация
    paginator = Paginator(blasts, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    # Статистика
    stats = {
        'total_blasts': Blast.objects.filter(business=business).count(),
        'running_blasts': Blast.objects.filter(business=business, status=BlastStatus.RUNNING).count(),
        'completed_blasts': Blast.objects.filter(business=business, status=BlastStatus.COMPLETED).count(),
        'total_sent': Blast.objects.filter(business=business).aggregate(
            total=Sum('sent_count')
        )['total'] or 0
    }
    
    context = {
        'business': business,
        'page_obj': page_obj,
        'stats': stats,
        'status_filter': status_filter,
        'trigger_filter': trigger_filter,
        'search': search,
        'status_choices': BlastStatus.choices,
        'trigger_choices': BlastTrigger.choices,
    }
    
    return render(request, 'blasts/list.html', context)


@login_required
def blast_create(request):
    """Создание рассылки"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    business = get_object_or_404(Business, id=biz_id, owner=request.user)
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        segment_id = request.POST.get('segment_id')
        trigger = request.POST.get('trigger', BlastTrigger.MANUAL)
        schedule_at = request.POST.get('schedule_at')
        budget_cap = request.POST.get('budget_cap')
        
        # Стратегия каскада
        strategy = {
            'cascade': [],
            'stop_on': [],
            'quiet_hours': {
                'start': request.POST.get('quiet_hours_start', '21:00'),
                'end': request.POST.get('quiet_hours_end', '09:00'),
                'timezone': 'Asia/Almaty'
            },
            'max_cost_per_recipient': float(request.POST.get('max_cost_per_recipient', 10))
        }
        
        # Построение каскада каналов
        channels = request.POST.getlist('channels')
        for channel in channels:
            timeout = int(request.POST.get(f'timeout_{channel}', 60))
            strategy['cascade'].append({
                'channel': channel,
                'timeout_min': timeout
            })
        
        # Условия остановки
        if request.POST.get('stop_on_delivered_and_clicked'):
            strategy['stop_on'].append('delivered_and_clicked')
        if request.POST.get('stop_on_redeemed'):
            strategy['stop_on'].append('redeemed')
        
        if not name:
            messages.error(request, 'Название рассылки обязательно.')
        elif not channels:
            messages.error(request, 'Выберите хотя бы один канал для рассылки.')
        else:
            # Создаем рассылку
            blast = Blast.objects.create(
                business=business,
                name=name,
                description=description,
                trigger=trigger,
                segment_id=segment_id if segment_id else None,
                strategy=strategy,
                schedule_at=timezone.datetime.fromisoformat(schedule_at) if schedule_at else None,
                budget_cap=float(budget_cap) if budget_cap else None
            )
            
            messages.success(request, f'Рассылка "{name}" создана успешно.')
            return redirect('blasts:detail', pk=blast.pk)
    
    # GET запрос - показываем форму
    segments = Segment.objects.filter(business=business, enabled=True)
    
    context = {
        'business': business,
        'segments': segments,
        'trigger_choices': BlastTrigger.choices,
    }
    
    return render(request, 'blasts/create.html', context)


@login_required
def blast_detail(request, pk):
    """Детали рассылки"""
    blast = get_object_or_404(Blast, pk=pk, business__owner=request.user)
    
    # Получаем аналитику
    analytics = get_blast_analytics(blast)
    
    # Последние получатели
    recent_recipients = BlastRecipient.objects.filter(blast=blast).select_related(
        'customer'
    ).order_by('-updated_at')[:10]
    
    # Последние попытки доставки
    recent_attempts = DeliveryAttempt.objects.filter(
        blast_recipient__blast=blast
    ).select_related('contact_point', 'blast_recipient__customer').order_by('-id')[:20]
    
    context = {
        'blast': blast,
        'analytics': analytics,
        'recent_recipients': recent_recipients,
        'recent_attempts': recent_attempts,
    }
    
    return render(request, 'blasts/detail.html', context)


@login_required
def blast_edit(request, pk):
    """Редактирование рассылки"""
    blast = get_object_or_404(Blast, pk=pk, business__owner=request.user)
    
    if blast.status not in [BlastStatus.DRAFT, BlastStatus.PAUSED]:
        messages.error(request, 'Можно редактировать только черновики и приостановленные рассылки.')
        return redirect('blasts:detail', pk=pk)
    
    if request.method == 'POST':
        blast.name = request.POST.get('name', blast.name)
        blast.description = request.POST.get('description', blast.description)
        
        segment_id = request.POST.get('segment_id')
        blast.segment_id = segment_id if segment_id else None
        
        schedule_at = request.POST.get('schedule_at')
        blast.schedule_at = timezone.datetime.fromisoformat(schedule_at) if schedule_at else None
        
        budget_cap = request.POST.get('budget_cap')
        blast.budget_cap = float(budget_cap) if budget_cap else None
        
        blast.save()
        messages.success(request, 'Рассылка обновлена.')
        return redirect('blasts:detail', pk=pk)
    
    segments = Segment.objects.filter(business=blast.business, enabled=True)
    
    context = {
        'blast': blast,
        'segments': segments,
    }
    
    return render(request, 'blasts/edit.html', context)


@login_required
@require_http_methods(["POST"])
def blast_start(request, pk):
    """Запуск рассылки"""
    blast = get_object_or_404(Blast, pk=pk, business__owner=request.user)
    
    if not blast.can_start():
        messages.error(request, f'Нельзя запустить рассылку в статусе "{blast.get_status_display()}".')
        return redirect('blasts:detail', pk=pk)
    
    # Запускаем асинхронно
    try:
        run_sync_fallback(start_blast_task, blast.id)
        messages.success(request, 'Рассылка запущена.')
    except Exception as e:
        messages.error(request, f'Ошибка запуска рассылки: {e}')
    
    return redirect('blasts:detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def blast_pause(request, pk):
    """Приостановка рассылки"""
    blast = get_object_or_404(Blast, pk=pk, business__owner=request.user)
    
    if blast.status != BlastStatus.RUNNING:
        messages.error(request, 'Можно приостановить только активную рассылку.')
        return redirect('blasts:detail', pk=pk)
    
    try:
        run_sync_fallback(pause_blast_task, blast.id)
        messages.success(request, 'Рассылка приостановлена.')
    except Exception as e:
        messages.error(request, f'Ошибка приостановки рассылки: {e}')
    
    return redirect('blasts:detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def blast_resume(request, pk):
    """Возобновление рассылки"""
    blast = get_object_or_404(Blast, pk=pk, business__owner=request.user)
    
    if blast.status != BlastStatus.PAUSED:
        messages.error(request, 'Можно возобновить только приостановленную рассылку.')
        return redirect('blasts:detail', pk=pk)
    
    try:
        run_sync_fallback(resume_blast_task, blast.id)
        messages.success(request, 'Рассылка возобновлена.')
    except Exception as e:
        messages.error(request, f'Ошибка возобновления рассылки: {e}')
    
    return redirect('blasts:detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def blast_cancel(request, pk):
    """Отмена рассылки"""
    blast = get_object_or_404(Blast, pk=pk, business__owner=request.user)
    
    if blast.status in [BlastStatus.COMPLETED, BlastStatus.CANCELLED]:
        messages.error(request, 'Рассылка уже завершена.')
        return redirect('blasts:detail', pk=pk)
    
    try:
        run_sync_fallback(cancel_blast_task, blast.id)
        messages.success(request, 'Рассылка отменена.')
    except Exception as e:
        messages.error(request, f'Ошибка отмены рассылки: {e}')
    
    return redirect('blasts:detail', pk=pk)


@login_required
def blast_analytics(request, pk):
    """Подробная аналитика рассылки"""
    blast = get_object_or_404(Blast, pk=pk, business__owner=request.user)
    
    analytics = get_blast_analytics(blast)
    
    return JsonResponse(analytics)


@login_required
def blast_export(request, pk):
    """Экспорт результатов рассылки"""
    blast = get_object_or_404(Blast, pk=pk, business__owner=request.user)
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="blast_{blast.id}_results.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Получатель', 'Телефон', 'Канал', 'Статус', 'Отправлено', 
        'Доставлено', 'Открыто', 'Клик', 'Стоимость'
    ])
    
    attempts = DeliveryAttempt.objects.filter(
        blast_recipient__blast=blast
    ).select_related('contact_point', 'blast_recipient__customer')
    
    for attempt in attempts:
        writer.writerow([
            attempt.blast_recipient.customer.phone_e164,
            attempt.contact_point.value,
            attempt.get_channel_display(),
            attempt.get_status_display(),
            attempt.sent_at.strftime('%Y-%m-%d %H:%M') if attempt.sent_at else '',
            attempt.delivered_at.strftime('%Y-%m-%d %H:%M') if attempt.delivered_at else '',
            attempt.opened_at.strftime('%Y-%m-%d %H:%M') if attempt.opened_at else '',
            attempt.clicked_at.strftime('%Y-%m-%d %H:%M') if attempt.clicked_at else '',
            str(attempt.cost)
        ])
    
    return response


@login_required
def template_list(request):
    """Список шаблонов сообщений"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    business = get_object_or_404(Business, id=biz_id, owner=request.user)
    
    templates = MessageTemplate.objects.filter(business=business).order_by('-created_at')
    
    # Фильтры
    channel_filter = request.GET.get('channel', '')
    if channel_filter:
        templates = templates.filter(channel=channel_filter)
    
    context = {
        'business': business,
        'templates': templates,
        'channel_filter': channel_filter,
    }
    
    return render(request, 'blasts/templates/list.html', context)


@login_required
def template_create(request):
    """Создание шаблона сообщения"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    business = get_object_or_404(Business, id=biz_id, owner=request.user)
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        channel = request.POST.get('channel')
        locale = request.POST.get('locale', 'ru')
        subject = request.POST.get('subject', '').strip()
        body_text = request.POST.get('body_text', '').strip()
        body_html = request.POST.get('body_html', '').strip()
        
        if not name or not channel or not body_text:
            messages.error(request, 'Заполните обязательные поля.')
        else:
            template = MessageTemplate.objects.create(
                business=business,
                name=name,
                channel=channel,
                locale=locale,
                subject=subject,
                body_text=body_text,
                body_html=body_html
            )
            
            messages.success(request, f'Шаблон "{name}" создан.')
            return redirect('blasts:template_detail', pk=template.pk)
    
    from .models import ContactPointType
    
    context = {
        'business': business,
        'channel_choices': ContactPointType.choices,
    }
    
    return render(request, 'blasts/templates/create.html', context)


@login_required
def template_detail(request, pk):
    """Детали шаблона"""
    template = get_object_or_404(MessageTemplate, pk=pk, business__owner=request.user)
    
    context = {
        'template': template,
    }
    
    return render(request, 'blasts/templates/detail.html', context)


@login_required
def template_edit(request, pk):
    """Редактирование шаблона"""
    template = get_object_or_404(MessageTemplate, pk=pk, business__owner=request.user)
    
    if request.method == 'POST':
        template.name = request.POST.get('name', template.name)
        template.subject = request.POST.get('subject', template.subject)
        template.body_text = request.POST.get('body_text', template.body_text)
        template.body_html = request.POST.get('body_html', template.body_html)
        template.is_active = bool(request.POST.get('is_active'))
        
        template.save()
        messages.success(request, 'Шаблон обновлен.')
        return redirect('blasts:template_detail', pk=pk)
    
    context = {
        'template': template,
    }
    
    return render(request, 'blasts/templates/edit.html', context)


@login_required
def contact_point_list(request):
    """Список контактных точек"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    business = get_object_or_404(Business, id=biz_id, owner=request.user)
    
    contacts = ContactPoint.objects.filter(business=business).select_related('customer')
    
    # Фильтры
    type_filter = request.GET.get('type', '')
    verified_filter = request.GET.get('verified', '')
    
    if type_filter:
        contacts = contacts.filter(type=type_filter)
    
    if verified_filter:
        contacts = contacts.filter(verified=verified_filter == 'true')
    
    # Статистика
    stats = ContactPoint.objects.filter(business=business).aggregate(
        total=Count('id'),
        verified=Count('id', filter=Q(verified=True)),
        opt_in=Count('id', filter=Q(opt_in=True)),
    )
    
    # Группировка по типам
    type_stats = ContactPoint.objects.filter(business=business).values('type').annotate(
        count=Count('id')
    ).order_by('type')
    
    context = {
        'business': business,
        'contacts': contacts,
        'stats': stats,
        'type_stats': type_stats,
        'type_filter': type_filter,
        'verified_filter': verified_filter,
    }
    
    return render(request, 'blasts/contacts/list.html', context)


@login_required
@require_http_methods(["POST"])
def contact_sync(request):
    """Синхронизация контактных точек"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        return JsonResponse({'success': False, 'error': 'Бизнес не выбран'})
    
    business = get_object_or_404(Business, id=biz_id, owner=request.user)
    
    try:
        # Запускаем синхронизацию
        result = run_sync_fallback(sync_contact_points_task, business.id)
        
        if hasattr(result, 'get'):  # Celery result
            return JsonResponse({'success': True, 'message': 'Синхронизация запущена'})
        else:  # Синхронный результат
            return JsonResponse({
                'success': True, 
                'message': f'Синхронизация завершена: создано {result.get("created", 0)}, обновлено {result.get("updated", 0)}'
            })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def short_link_redirect(request, short_code):
    """Редирект по короткой ссылке"""
    original_url = process_short_link_click(short_code, request)
    
    if original_url:
        return HttpResponseRedirect(original_url)
    else:
        raise Http404("Ссылка не найдена или истекла")


@csrf_exempt
@require_http_methods(["POST"])
def delivery_webhook(request):
    """Webhook для обновления статусов доставки"""
    try:
        data = json.loads(request.body)
        
        external_id = data.get('external_id')
        status = data.get('status')
        metadata = data.get('metadata', {})
        
        if external_id and status:
            handle_delivery_webhook(external_id, status, metadata)
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'error': 'Missing required fields'})
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
