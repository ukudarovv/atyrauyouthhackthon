from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.utils import timezone
import json

from apps.businesses.models import Business
from apps.campaigns.models import Campaign
from apps.customers.models import Customer
from .models import MysteryDrop, MysteryDropTier, MysteryDropAttempt, PowerHour
from .services import attempt_mystery_drop, start_power_hour
from .tasks import run_sync_fallback


def mystery_drop_landing(request, campaign_slug):
    """Публичный лендинг Mystery Drop"""
    campaign = get_object_or_404(Campaign, slug=campaign_slug, is_active=True)
    
    # Находим активный Mystery Drop для кампании
    mystery_drop = MysteryDrop.objects.filter(
        campaign=campaign,
        enabled=True
    ).first()
    
    if not mystery_drop or not mystery_drop.is_active():
        return render(request, 'growth/mystery_inactive.html', {
            'campaign': campaign,
            'message': 'Mystery Drop в данный момент неактивен'
        })
    
    context = {
        'campaign': campaign,
        'mystery_drop': mystery_drop,
        'tiers': mystery_drop.tiers.filter(is_active=True).order_by('order'),
    }
    
    return render(request, 'growth/mystery_landing.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def mystery_drop_attempt(request, mystery_drop_id):
    """API для попытки в Mystery Drop"""
    
    try:
        data = json.loads(request.body)
        phone = data.get('phone', '').strip()
        
        if not phone:
            return JsonResponse({
                'success': False,
                'message': 'Укажите номер телефона'
            })
        
        mystery_drop = get_object_or_404(MysteryDrop, id=mystery_drop_id)
        
        # Делаем попытку
        success, message, result_data = attempt_mystery_drop(mystery_drop, phone, request)
        
        return JsonResponse({
            'success': success,
            'message': message,
            'data': result_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': 'Произошла ошибка, попробуйте позже'
        })


@login_required
def mystery_drop_list(request):
    """Список Mystery Drops"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    business = get_object_or_404(Business, id=biz_id, owner=request.user)
    
    mystery_drops = MysteryDrop.objects.filter(business=business).select_related('campaign')
    
    # Фильтры
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        mystery_drops = mystery_drops.filter(enabled=True)
    elif status_filter == 'inactive':
        mystery_drops = mystery_drops.filter(enabled=False)
    
    context = {
        'business': business,
        'mystery_drops': mystery_drops,
        'status_filter': status_filter,
    }
    
    return render(request, 'growth/mystery_drop_list.html', context)


@login_required
def mystery_drop_create(request):
    """Создание Mystery Drop"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    business = get_object_or_404(Business, id=biz_id, owner=request.user)
    
    if request.method == 'POST':
        campaign_id = request.POST.get('campaign_id')
        title = request.POST.get('title', '').strip()
        
        if not campaign_id or not title:
            messages.error(request, 'Заполните обязательные поля.')
        else:
            campaign = get_object_or_404(Campaign, id=campaign_id, business=business)
            
            mystery_drop = MysteryDrop.objects.create(
                business=business,
                campaign=campaign,
                title=title,
                subtitle=request.POST.get('subtitle', ''),
                daily_cap_per_phone=int(request.POST.get('daily_cap_per_phone', 1)),
                daily_cap_total=int(request.POST.get('daily_cap_total', 1000)),
                auto_wallet_creation=bool(request.POST.get('auto_wallet_creation')),
                send_notification=bool(request.POST.get('send_notification'))
            )
            
            messages.success(request, f'Mystery Drop "{title}" создан.')
            return redirect('growth:mystery_drop_detail', pk=mystery_drop.pk)
    
    campaigns = Campaign.objects.filter(business=business, is_active=True)
    
    context = {
        'business': business,
        'campaigns': campaigns,
    }
    
    return render(request, 'growth/mystery_drop_create.html', context)


@login_required
def mystery_drop_detail(request, pk):
    """Детали Mystery Drop"""
    mystery_drop = get_object_or_404(MysteryDrop, pk=pk, business__owner=request.user)
    
    # Статистика за последние 7 дней
    stats_7d = []
    for i in range(7):
        date = timezone.now().date() - timezone.timedelta(days=i)
        daily_stats = mystery_drop.get_daily_stats(date)
        daily_stats['date'] = date
        stats_7d.append(daily_stats)
    
    # Последние попытки
    recent_attempts = MysteryDropAttempt.objects.filter(
        mystery_drop=mystery_drop
    ).select_related('tier', 'customer').order_by('-created_at')[:20]
    
    context = {
        'mystery_drop': mystery_drop,
        'stats_7d': stats_7d,
        'recent_attempts': recent_attempts,
    }
    
    return render(request, 'growth/mystery_drop_detail.html', context)


@login_required
def power_hour_list(request):
    """Список Power Hours"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    business = get_object_or_404(Business, id=biz_id, owner=request.user)
    
    power_hours = PowerHour.objects.filter(business=business).select_related('campaign')
    
    context = {
        'business': business,
        'power_hours': power_hours,
    }
    
    return render(request, 'growth/power_hour_list.html', context)


@login_required
def power_hour_create(request):
    """Создание Power Hour"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    business = get_object_or_404(Business, id=biz_id, owner=request.user)
    
    if request.method == 'POST':
        campaign_id = request.POST.get('campaign_id')
        title = request.POST.get('title', '').strip()
        starts_at = request.POST.get('starts_at')
        
        if not campaign_id or not title or not starts_at:
            messages.error(request, 'Заполните обязательные поля.')
        else:
            campaign = get_object_or_404(Campaign, id=campaign_id, business=business)
            
            power_hour = PowerHour.objects.create(
                business=business,
                campaign=campaign,
                title=title,
                discount_text=request.POST.get('discount_text', ''),
                duration_minutes=int(request.POST.get('duration_minutes', 60)),
                starts_at=timezone.datetime.fromisoformat(starts_at),
                auto_wallet_update=bool(request.POST.get('auto_wallet_update')),
                send_blast=bool(request.POST.get('send_blast'))
            )
            
            messages.success(request, f'Power Hour "{title}" создан.')
            return redirect('growth:power_hour_detail', pk=power_hour.pk)
    
    campaigns = Campaign.objects.filter(business=business, is_active=True)
    
    context = {
        'business': business,
        'campaigns': campaigns,
    }
    
    return render(request, 'growth/power_hour_create.html', context)


@login_required
def power_hour_detail(request, pk):
    """Детали Power Hour"""
    power_hour = get_object_or_404(PowerHour, pk=pk, business__owner=request.user)
    
    context = {
        'power_hour': power_hour,
    }
    
    return render(request, 'growth/power_hour_detail.html', context)


@login_required
@require_http_methods(["POST"])
def power_hour_start(request, pk):
    """Запуск Power Hour"""
    power_hour = get_object_or_404(PowerHour, pk=pk, business__owner=request.user)
    
    if power_hour.can_start():
        success = start_power_hour(power_hour)
        if success:
            messages.success(request, f'Power Hour "{power_hour.title}" запущен!')
        else:
            messages.error(request, 'Не удалось запустить Power Hour.')
    else:
        messages.error(request, 'Power Hour нельзя запустить в данный момент.')
    
    return redirect('growth:power_hour_detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def power_hour_cancel(request, pk):
    """Отмена Power Hour"""
    power_hour = get_object_or_404(PowerHour, pk=pk, business__owner=request.user)
    
    if power_hour.status in ['scheduled', 'running']:
        power_hour.status = 'cancelled'
        power_hour.save()
        messages.success(request, f'Power Hour "{power_hour.title}" отменен.')
    else:
        messages.error(request, 'Power Hour нельзя отменить.')
    
    return redirect('growth:power_hour_detail', pk=pk)


@login_required
def growth_analytics(request):
    """Аналитика Growth механик"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    business = get_object_or_404(Business, id=biz_id, owner=request.user)
    
    # Mystery Drop статистика
    mystery_stats = {
        'total_drops': MysteryDrop.objects.filter(business=business).count(),
        'active_drops': MysteryDrop.objects.filter(business=business, enabled=True).count(),
        'total_attempts': MysteryDropAttempt.objects.filter(mystery_drop__business=business).count(),
        'total_wins': MysteryDropAttempt.objects.filter(mystery_drop__business=business, won=True).count(),
    }
    
    # Power Hour статистика
    power_stats = {
        'total_hours': PowerHour.objects.filter(business=business).count(),
        'completed_hours': PowerHour.objects.filter(business=business, status='completed').count(),
        'total_blast_sent': PowerHour.objects.filter(business=business).aggregate(
            total=Sum('blast_sent')
        )['total'] or 0,
    }
    
    # Streak статистика
    streak_stats = Customer.objects.filter(business=business).aggregate(
        avg_streak=Count('streak_count'),
        max_streak=Count('streak_best'),
        active_streaks=Count('id', filter=Q(streak_count__gt=0))
    )
    
    context = {
        'business': business,
        'mystery_stats': mystery_stats,
        'power_stats': power_stats,
        'streak_stats': streak_stats,
    }
    
    return render(request, 'growth/analytics.html', context)


@login_required
def streaks_overview(request):
    """Обзор серий клиентов"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    business = get_object_or_404(Business, id=biz_id, owner=request.user)
    
    # Топ клиенты по сериям
    top_customers = Customer.objects.filter(
        business=business,
        streak_count__gt=0
    ).order_by('-streak_count')[:20]
    
    # Распределение по длине серий
    streak_distribution = Customer.objects.filter(business=business).extra(
        select={
            'streak_range': """
                CASE 
                    WHEN streak_count = 0 THEN '0'
                    WHEN streak_count BETWEEN 1 AND 2 THEN '1-2'
                    WHEN streak_count BETWEEN 3 AND 5 THEN '3-5'
                    WHEN streak_count BETWEEN 6 AND 10 THEN '6-10'
                    WHEN streak_count > 10 THEN '10+'
                END
            """
        }
    ).values('streak_range').annotate(count=Count('id')).order_by('streak_range')
    
    context = {
        'business': business,
        'top_customers': top_customers,
        'streak_distribution': streak_distribution,
    }
    
    return render(request, 'growth/streaks_overview.html', context)
