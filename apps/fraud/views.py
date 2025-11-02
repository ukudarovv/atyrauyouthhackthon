from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from apps.businesses.models import Business
from .models import RiskEvent, RiskDecision

@login_required
def risk_list(request):
    """Журнал рисков с фильтрами"""
    # Проверка ролей
    if not (request.user.is_superuser or request.user.role in ('manager', 'owner')):
        raise PermissionDenied('Недостаточно прав для просмотра журнала рисков')

    # Получаем бизнес пользователя
    if request.user.is_superuser:
        # Суперпользователь может видеть все
        qs = RiskEvent.objects.all()
        businesses = Business.objects.all()
    else:
        # Обычный пользователь видит только свои бизнесы
        businesses = request.user.owned_businesses.all()
        qs = RiskEvent.objects.filter(business__in=businesses)

    qs = qs.select_related('business', 'coupon', 'coupon__campaign').order_by('-created_at')
    
    # Фильтры
    business_id = request.GET.get('business')
    if business_id:
        qs = qs.filter(business_id=business_id)
    
    kind = request.GET.get('kind')
    if kind:
        qs = qs.filter(kind=kind)
        
    decision = request.GET.get('decision')
    if decision:
        qs = qs.filter(decision=decision)
        
    phone = request.GET.get('phone')
    if phone:
        qs = qs.filter(phone__icontains=phone)
        
    ip = request.GET.get('ip')
    if ip:
        qs = qs.filter(ip__icontains=ip)
    
    resolved = request.GET.get('resolved')
    if resolved == '1':
        qs = qs.filter(resolved=True)
    elif resolved == '0':
        qs = qs.filter(resolved=False)

    # Пагинация
    page_obj = Paginator(qs, 30).get_page(request.GET.get('page'))
    
    # Статистика
    stats = {
        'total': qs.count(),
        'blocks': qs.filter(decision=RiskDecision.BLOCK).count(),
        'warns': qs.filter(decision=RiskDecision.WARN).count(),
        'unresolved': qs.filter(resolved=False).count(),
    }
    
    context = {
        'page_obj': page_obj,
        'businesses': businesses,
        'stats': stats,
        'current_business': business_id,
        'current_kind': kind,
        'current_decision': decision,
        'current_phone': phone,
        'current_ip': ip,
        'current_resolved': resolved,
    }
    
    return render(request, 'fraud/list.html', context)

@login_required
def risk_resolve(request, pk: int):
    """Помечает событие риска как обработанное"""
    # Проверка ролей
    if not (request.user.is_superuser or request.user.role in ('manager', 'owner')):
        raise PermissionDenied('Недостаточно прав')

    if request.user.is_superuser:
        event = get_object_or_404(RiskEvent, id=pk)
    else:
        event = get_object_or_404(RiskEvent, id=pk, business__owner=request.user)
    
    event.resolved = True
    event.save(update_fields=['resolved'])
    
    messages.success(request, 'Событие помечено как обработанное.')
    return redirect('fraud:list')

@login_required
def denies_add(request):
    """Добавляет IP/телефон в черный список"""
    if request.method != 'POST':
        return redirect('fraud:list')
    
    # Проверка ролей
    if not (request.user.is_superuser or request.user.role in ('manager', 'owner')):
        raise PermissionDenied('Недостаточно прав')
    
    dtype = request.POST.get('type')  # ip|phone|utm
    value = (request.POST.get('value') or '').strip()
    business_id = request.POST.get('business_id')
    
    if not dtype or not value or not business_id:
        messages.error(request, 'Некорректные данные.')
        return redirect('fraud:list')
    
    # Проверяем доступ к бизнесу
    if request.user.is_superuser:
        business = get_object_or_404(Business, id=business_id)
    else:
        business = get_object_or_404(Business, id=business_id, owner=request.user)
    
    # Обновляем настройки
    settings = business.settings or {}
    fraud = settings.get('fraud', {})
    key = f"{dtype}_deny"
    
    if key not in fraud:
        fraud[key] = []
    
    if value and value not in fraud[key]:
        fraud[key].append(value)
        settings['fraud'] = fraud
        business.settings = settings
        business.save(update_fields=['settings'])
        
        messages.success(request, f'Добавлено в черный список: {dtype}={value}')
    else:
        messages.info(request, f'Значение уже в черном списке: {dtype}={value}')
    
    return redirect('fraud:list')
