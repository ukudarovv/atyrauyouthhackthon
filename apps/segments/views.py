"""
Views для управления сегментами клиентов
"""
import json
import logging
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator

from apps.businesses.models import Business
from .models import Segment, SegmentMember, SegmentKind
try:
    from .tasks import rebuild_segment, create_system_segments
except ImportError:
    # Fallback если Celery не доступен
    rebuild_segment = None
    create_system_segments = None
from .services import (
    build_queryset, mask_phone, get_segment_insights, 
    validate_segment_definition
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
def seg_list(request):
    """Список всех сегментов"""
    # Проверяем права доступа
    if not (request.user.is_superuser or request.user.role in ('manager', 'owner')):
        raise PermissionDenied('Недостаточно прав для просмотра сегментов')
    
    business = _get_current_business(request)
    if not business:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    # Создаем системные сегменты если их нет
    if not Segment.objects.filter(business=business, kind=SegmentKind.SYSTEM).exists():
        if create_system_segments:
            try:
                create_system_segments.delay(business.id)
                messages.info(request, 'Создаются системные сегменты, обновите страницу через минуту.')
            except Exception as e:
                logger.warning(f'Celery недоступен, создаем сегменты синхронно: {e}')
                # Создаем синхронно
                from .services import create_system_segments_sync
                created_count = create_system_segments_sync(business.id)
                messages.success(request, f'Создано системных сегментов: {created_count}')
        else:
            # Создаем синхронно если Celery недоступен
            from .services import create_system_segments_sync
            created_count = create_system_segments_sync(business.id)
            messages.success(request, f'Создано системных сегментов: {created_count}')
    
    # Получаем сегменты с пагинацией
    segments_qs = Segment.objects.filter(business=business).order_by('kind', '-last_built_at', 'name')
    
    # Фильтры
    kind_filter = request.GET.get('kind')
    if kind_filter:
        segments_qs = segments_qs.filter(kind=kind_filter)
    
    enabled_filter = request.GET.get('enabled')
    if enabled_filter == '1':
        segments_qs = segments_qs.filter(enabled=True)
    elif enabled_filter == '0':
        segments_qs = segments_qs.filter(enabled=False)
    
    # Пагинация
    paginator = Paginator(segments_qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    # Добавляем инсайты для каждого сегмента
    segments_with_data = []
    for segment in page_obj.object_list:
        try:
            insights = get_segment_insights(segment)
            segments_with_data.append({
                'segment': segment,
                'insights': insights
            })
        except Exception as e:
            logger.error(f"Error getting insights for segment {segment.id}: {e}")
            segments_with_data.append({
                'segment': segment,
                'insights': {'size': 0, 'error': str(e)}
            })
    
    context = {
        'page_obj': page_obj,
        'segments_data': segments_with_data,
        'business': business,
        'current_kind': kind_filter,
        'current_enabled': enabled_filter,
    }
    
    return render(request, 'segments/list.html', context)


@login_required
def seg_edit(request, pk=None):
    """Создание/редактирование сегмента"""
    # Проверяем права доступа
    if not (request.user.is_superuser or request.user.role in ('manager', 'owner')):
        raise PermissionDenied('Недостаточно прав для редактирования сегментов')
    
    business = _get_current_business(request)
    if not business:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    if request.method == 'POST':
        if pk:
            segment = get_object_or_404(Segment, id=pk, business=business)
            # Системные сегменты нельзя редактировать
            if segment.kind == SegmentKind.SYSTEM:
                messages.error(request, 'Системные сегменты нельзя редактировать.')
                return redirect('segments:list')
        else:
            segment = Segment(business=business, kind=SegmentKind.CUSTOM)
        
        # Обновляем поля
        segment.name = request.POST.get('name', '').strip() or 'Новый сегмент'
        segment.slug = request.POST.get('slug', '').strip()
        segment.description = request.POST.get('description', '').strip()
        segment.color = request.POST.get('color', '#3B82F6')
        segment.enabled = bool(request.POST.get('enabled'))
        segment.is_dynamic = True
        
        # Парсим и валидируем JSON правила
        definition_text = request.POST.get('definition', '{}').strip()
        try:
            definition = json.loads(definition_text)
            
            # Валидируем определение
            is_valid, error_msg = validate_segment_definition(definition)
            if not is_valid:
                messages.error(request, f'Ошибка в правилах сегмента: {error_msg}')
                context = {
                    'segment': segment,
                    'definition_text': definition_text,
                    'business': business
                }
                return render(request, 'segments/edit.html', context)
            
            segment.definition = definition
            
        except json.JSONDecodeError as e:
            messages.error(request, f'Некорректный JSON в правилах: {str(e)}')
            context = {
                'segment': segment,
                'definition_text': definition_text,
                'business': business
            }
            return render(request, 'segments/edit.html', context)
        
        try:
            segment.save()
            
            # Запускаем перестроение
            if rebuild_segment:
                try:
                    rebuild_segment.delay(segment.id)
                    action = 'обновлен' if pk else 'создан'
                    messages.success(request, f'Сегмент "{segment.name}" {action} и поставлен в очередь на перестроение.')
                except Exception as e:
                    logger.warning(f'Celery недоступен, перестраиваем синхронно: {e}')
                    from .services import rebuild_segment_sync
                    rebuild_segment_sync(segment.id)
                    action = 'обновлен' if pk else 'создан'
                    messages.success(request, f'Сегмент "{segment.name}" {action} и перестроен.')
            else:
                # Перестраиваем синхронно если Celery недоступен
                from .services import rebuild_segment_sync
                rebuild_segment_sync(segment.id)
                action = 'обновлен' if pk else 'создан'
                messages.success(request, f'Сегмент "{segment.name}" {action} и перестроен.')
            
            return redirect('segments:list')
            
        except Exception as e:
            logger.error(f"Error saving segment: {e}")
            messages.error(request, f'Ошибка сохранения сегмента: {str(e)}')
    
    # GET запрос - показываем форму
    if pk:
        segment = get_object_or_404(Segment, id=pk, business=business)
        if segment.kind == SegmentKind.SYSTEM:
            messages.warning(request, 'Вы просматриваете системный сегмент. Редактирование недоступно.')
    else:
        segment = Segment(business=business, kind=SegmentKind.CUSTOM)
    
    # Получаем инсайты если сегмент существует
    insights = None
    if segment.id:
        try:
            insights = get_segment_insights(segment)
        except Exception as e:
            logger.error(f"Error getting insights for segment {segment.id}: {e}")
    
    # Подготавливаем JSON для формы
    definition_text = json.dumps(segment.definition, indent=2, ensure_ascii=False) if segment.definition else json.dumps({
        "logic": "all",
        "conds": [
            {"field": "recency_days", "op": "<=", "value": 14}
        ]
    }, indent=2, ensure_ascii=False)
    
    context = {
        'segment': segment,
        'definition_text': definition_text,
        'insights': insights,
        'business': business,
        'is_editing': bool(pk),
        'can_edit': segment.kind != SegmentKind.SYSTEM
    }
    
    return render(request, 'segments/edit.html', context)


@login_required
def seg_preview(request, pk):
    """AJAX превью сегмента"""
    business = _get_current_business(request)
    if not business:
        return JsonResponse({'error': 'Бизнес не выбран'}, status=400)
    
    segment = get_object_or_404(Segment, id=pk, business=business)
    
    try:
        # Строим QuerySet
        customers_qs = build_queryset(business, segment.definition)
        
        # Получаем превью
        sample_customers = list(customers_qs.values(
            'phone_e164', 'redeems_count', 'recency_days', 
            'r_score', 'f_score', 'm_score'
        )[:50])
        
        # Маскируем телефоны
        for customer in sample_customers:
            customer['phone_masked'] = mask_phone(customer['phone_e164'])
            del customer['phone_e164']
        
        return JsonResponse({
            'success': True,
            'count': customers_qs.count(),
            'customers': sample_customers
        })
        
    except Exception as e:
        logger.error(f"Error previewing segment {pk}: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def seg_rebuild(request, pk):
    """Запуск перестроения сегмента"""
    business = _get_current_business(request)
    if not business:
        messages.error(request, 'Бизнес не выбран.')
        return redirect('segments:list')
    
    segment = get_object_or_404(Segment, id=pk, business=business)
    
    if rebuild_segment:
        try:
            rebuild_segment.delay(segment.id)
            messages.success(request, f'Запущено перестроение сегмента "{segment.name}".')
        except Exception as e:
            logger.warning(f'Celery недоступен, перестраиваем синхронно: {e}')
            from .services import rebuild_segment_sync
            rebuild_segment_sync(segment.id)
            messages.success(request, f'Сегмент "{segment.name}" перестроен.')
    else:
        # Перестраиваем синхронно если Celery недоступен
        from .services import rebuild_segment_sync
        rebuild_segment_sync(segment.id)
        messages.success(request, f'Сегмент "{segment.name}" перестроен.')
    
    return redirect('segments:list')


@login_required
def seg_insights(request, pk):
    """AJAX получение инсайтов сегмента"""
    business = _get_current_business(request)
    if not business:
        return JsonResponse({'error': 'Бизнес не выбран'}, status=400)
    
    segment = get_object_or_404(Segment, id=pk, business=business)
    
    try:
        insights = get_segment_insights(segment)
        return JsonResponse({
            'success': True,
            'insights': insights
        })
    except Exception as e:
        logger.error(f"Error getting insights for segment {pk}: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
