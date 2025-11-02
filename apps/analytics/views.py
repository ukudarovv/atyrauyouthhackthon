from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.utils import timezone
import json

from apps.businesses.models import Business
from apps.campaigns.models import TrackEvent, TrackEventType
from .forms import DateRangeForm, CampaignFilterForm, default_range

def _get_business(request):
    """Получение текущего бизнеса пользователя"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        return None
    return Business.objects.filter(id=biz_id, owner=request.user).first()

def _range_qs(business, start, end, campaign_id=None):
    """Базовый queryset для диапазона дат"""
    qs = TrackEvent.objects.filter(
        business=business, 
        created_at__date__gte=start, 
        created_at__date__lte=end
    )
    if campaign_id:
        qs = qs.filter(campaign_id=campaign_id)
    return qs

def _cards_data(business, start, end, campaign_id=None):
    """Данные для карточек метрик"""
    qs = _range_qs(business, start, end, campaign_id)
    counts = qs.values('type').annotate(n=Count('id'))
    m = {c['type']: c['n'] for c in counts}

    views = m.get(TrackEventType.LANDING_VIEW, 0)
    clicks = m.get(TrackEventType.LANDING_CLICK, 0)
    issues = m.get(TrackEventType.COUPON_ISSUE, 0)
    redeems = m.get(TrackEventType.COUPON_REDEEM, 0)

    # Конверсии
    cr_click_issue = (issues / clicks * 100) if clicks else 0.0
    cr_issue_redeem = (redeems / issues * 100) if issues else 0.0

    return {
        'views': views,
        'clicks': clicks,
        'issues': issues,
        'redeems': redeems,
        'cr_click_issue': round(cr_click_issue, 1),
        'cr_issue_redeem': round(cr_issue_redeem, 1),
    }

def _series_data(business, start, end, campaign_id=None):
    """Данные для временных рядов"""
    qs = _range_qs(business, start, end, campaign_id)
    base = qs.annotate(d=TruncDate('created_at')).values('d','type').annotate(n=Count('id'))
    
    # Собираем словарь: {date: {type: n}}
    by_date = {}
    for row in base:
        d = row['d']
        by_date.setdefault(d, {})[row['type']] = row['n']

    # Нормализуем каждый день в диапазоне
    days = []
    cur = start
    while cur <= end:
        days.append(cur)
        cur += timezone.timedelta(days=1)

    points = []
    for d in days:
        bucket = by_date.get(d, {})
        points.append({
            'date': d.isoformat(),
            'view': bucket.get(TrackEventType.LANDING_VIEW, 0),
            'issue': bucket.get(TrackEventType.COUPON_ISSUE, 0),
            'redeem': bucket.get(TrackEventType.COUPON_REDEEM, 0),
        })
    return points

def _top_campaigns(business, start, end):
    """Топ кампаний за период"""
    qs = TrackEvent.objects.filter(
        business=business, 
        created_at__date__gte=start, 
        created_at__date__lte=end
    )
    
    # Агрегируем по кампании
    agg = qs.values('campaign_id', 'campaign__name').annotate(
        views=Count('id', filter=Q(type=TrackEventType.LANDING_VIEW)),
        clicks=Count('id', filter=Q(type=TrackEventType.LANDING_CLICK)),
        issues=Count('id', filter=Q(type=TrackEventType.COUPON_ISSUE)),
        redeems=Count('id', filter=Q(type=TrackEventType.COUPON_REDEEM)),
    ).order_by('-redeems','-issues','-views')[:20]

    # Считаем конверсии
    result = []
    for r in agg:
        # Пропускаем записи без кампании или без активности
        if not r['campaign__name'] and not any([r['views'], r['clicks'], r['issues'], r['redeems']]):
            continue
            
        cr1 = (r['issues']/r['clicks']*100) if r['clicks'] else 0.0
        cr2 = (r['redeems']/r['issues']*100) if r['issues'] else 0.0
        result.append({
            **r, 
            'cr_click_issue': round(cr1,1), 
            'cr_issue_redeem': round(cr2,1)
        })
    return result

@login_required
def dashboard(request):
    """Главная страница аналитики"""
    biz = _get_business(request)
    if not biz:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')

    # Инициализируем формы
    dr = DateRangeForm(request.GET or None)
    if dr.is_valid():
        start = dr.cleaned_data.get('start') or default_range()[0]
        end = dr.cleaned_data.get('end') or default_range()[1]
    else:
        start, end = default_range()

    cf = CampaignFilterForm(biz, request.GET or None)
    if cf.is_valid():
        campaign_id = cf.cleaned_data.get('campaign') or None
    else:
        campaign_id = None

    ctx = {
        'dr': dr, 
        'cf': cf, 
        'business': biz, 
        'campaign_id': campaign_id, 
        'start': start, 
        'end': end
    }
    return render(request, 'analytics/dashboard.html', ctx)

@login_required
def cards_partial(request):
    """Partial для карточек метрик"""
    biz = _get_business(request)
    if not biz:
        return render(request, 'analytics/_cards.html', {'data': {}})
        
    dr = DateRangeForm(request.GET)
    if dr.is_valid():
        start, end = dr.cleaned_data['start'], dr.cleaned_data['end']
    else:
        start, end = default_range()
        
    campaign_id = request.GET.get('campaign') or None
    if campaign_id:
        try:
            campaign_id = int(campaign_id)
        except (ValueError, TypeError):
            campaign_id = None

    data = _cards_data(biz, start, end, campaign_id)
    return render(request, 'analytics/_cards.html', {'data': data})

@login_required
def series_partial(request):
    """Partial для графика временных рядов"""
    biz = _get_business(request)
    if not biz:
        return render(request, 'analytics/_series.html', {'points': []})
        
    dr = DateRangeForm(request.GET)
    if dr.is_valid():
        start, end = dr.cleaned_data['start'], dr.cleaned_data['end']
    else:
        start, end = default_range()
        
    campaign_id = request.GET.get('campaign') or None
    if campaign_id:
        try:
            campaign_id = int(campaign_id)
        except (ValueError, TypeError):
            campaign_id = None

    points = _series_data(biz, start, end, campaign_id)
    return render(request, 'analytics/_series.html', {
        'points': json.dumps(points),
        'points_data': points
    })

@login_required
def top_campaigns_partial(request):
    """Partial для таблицы топ кампаний"""
    biz = _get_business(request)
    if not biz:
        return render(request, 'analytics/_top_campaigns.html', {'rows': []})
        
    dr = DateRangeForm(request.GET)
    if dr.is_valid():
        start, end = dr.cleaned_data['start'], dr.cleaned_data['end']
    else:
        start, end = default_range()
        
    rows = _top_campaigns(biz, start, end)
    return render(request, 'analytics/_top_campaigns.html', {'rows': rows})