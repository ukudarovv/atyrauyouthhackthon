from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from apps.campaigns.models import Campaign, Landing
from .models import AIJob, AIJobType, AIJobStatus
from .tasks import run_ai_job
import json
import logging

logger = logging.getLogger(__name__)

@login_required
@require_POST
def start_copywriting(request, campaign_id):
    """
    Запускает AI-копирайтинг для кампании
    """
    campaign = get_object_or_404(Campaign, id=campaign_id, business__owner=request.user)
    
    try:
        data = json.loads(request.body)
        custom_prompt = data.get('custom_prompt', '').strip()
        
        # Подготавливаем данные для AI
        input_data = {
            'campaign_name': campaign.name,
            'description': campaign.description or '',
            'audience': 'локальные жители',
            'custom_prompt': custom_prompt
        }
        
        # Создаем задачу
        job = AIJob.objects.create(
            user=request.user,
            campaign=campaign,
            job_type=AIJobType.GENERATE_COPY,
            input_data=input_data
        )
        
        # Запускаем синхронно (временно без Celery)
        result = run_ai_job(job.id)
        
        if result.get('success'):
            return JsonResponse({
                'success': True,
                'job_id': job.id,
                'message': 'AI-копирайтинг завершен'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Неизвестная ошибка')
            }, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Некорректные данные запроса'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def job_status(request, job_id):
    """
    Проверяет статус AI задачи
    """
    job = get_object_or_404(AIJob, id=job_id, user=request.user)
    
    response_data = {
        'job_id': job.id,
        'status': job.status,
        'job_type': job.job_type,
    }
    
    if job.status == AIJobStatus.COMPLETED:
        response_data['result'] = job.output_data
    elif job.status == AIJobStatus.FAILED:
        response_data['error'] = job.error_message
    
    return JsonResponse(response_data)

@login_required
@require_POST
def apply_copywriting(request, campaign_id):
    """
    Применяет результаты AI-копирайтинга к кампании
    """
    campaign = get_object_or_404(Campaign, id=campaign_id, business__owner=request.user)
    
    try:
        data = json.loads(request.body)
        
        # Получаем или создаем лендинг
        landing, created = Landing.objects.get_or_create(
            campaign=campaign,
            defaults={
                'headline': '',
                'body_md': '',
                'cta_text': 'Получить предложение'
            }
        )
        
        # Применяем выбранные варианты
        updated_fields = []
        
        if 'headline' in data:
            landing.headline = data['headline'][:100]  # Лимит длины
            updated_fields.append('headline')
        
        if 'cta_text' in data:
            landing.cta_text = data['cta_text'][:50]  # Лимит длины
            updated_fields.append('cta_text')
        
        if 'description' in data:
            landing.body_md = data['description'][:500]  # Лимит длины для описания
            updated_fields.append('description')
        
        if 'seo_title' in data:
            landing.seo_title = data['seo_title'][:60]  # Лимит длины
            updated_fields.append('seo_title')
        
        if 'seo_description' in data:
            landing.seo_desc = data['seo_description'][:160]  # Лимит длины
            updated_fields.append('seo_description')
        
        landing.save()
        
        # Логируем что было обновлено
        updated_text = ', '.join(updated_fields) if updated_fields else 'ничего'
        
        logger.info(f"AI copywriting applied to campaign {campaign.id}: {updated_text}")
        logger.info(f"Updated landing fields: {updated_fields}")
        
        return JsonResponse({
            'success': True,
            'message': f'Тексты применены к кампании ({updated_text})',
            'updated_fields': updated_fields
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
