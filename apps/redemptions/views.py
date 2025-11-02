from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q

from apps.coupons.models import Coupon
from apps.businesses.models import Business
from apps.campaigns.models import Campaign
from apps.fraud.services import score_redeem
from apps.fraud.models import RiskDecision
from .forms import RedeemForm
from .services import redeem_coupon, has_business_access, rate_limited
from .models import Redemption

@login_required
def redeem_view(request):
    """Форма погашения купона"""
    # Проверка ролей: cashier, manager, owner или superuser
    if not (request.user.is_superuser or request.user.role in ('cashier', 'manager', 'owner')):
        raise PermissionDenied('Недостаточно прав для погашения купонов')

    if request.method == 'POST':
        # Проверка rate-limit
        if rate_limited(request.user.id, 'redeem', limit=15, window_sec=60):
            messages.error(request, 'Слишком много попыток. Подождите минуту и повторите.')
            return redirect('redemptions:redeem')

        form = RedeemForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['code']
            
            try:
                coupon = Coupon.objects.select_related('campaign', 'campaign__business').get(code=code)
            except Coupon.DoesNotExist:
                messages.error(request, f'Купон с кодом "{code}" не найден')
                return render(request, 'redemptions/redeem_form.html', {'form': form})

            # Проверка доступа к бизнесу
            if not has_business_access(request.user, coupon.campaign.business):
                raise PermissionDenied('У вас нет доступа к этому бизнесу')

            # АНТИФРОД: скоринг на погашении
            score, reasons, decision = score_redeem(request, coupon=coupon)

            # если высокий риск — разрешаем только менеджеру/владельцу
            if decision == RiskDecision.BLOCK and request.user.role == 'cashier' and not request.user.is_superuser:
                messages.error(request, 'Высокий риск фрода. Обратитесь к менеджеру для подтверждения.')
                return redirect('redemptions:redeem')

            try:
                redemption = redeem_coupon(
                    coupon=coupon,
                    cashier=request.user,
                    amount=form.cleaned_data.get('amount'),
                    pos_ref=form.cleaned_data.get('pos_ref', ''),
                    note=form.cleaned_data.get('note', '')
                )
                
                # Показываем предупреждение если есть риск
                if decision != RiskDecision.ALLOW:
                    messages.warning(request, f'Погашено с предупреждением (risk={score}). Проверьте журнал рисков.')
                else:
                    messages.success(request, f'✅ Купон {coupon.code} успешно погашен!')
                
                # Показываем детали погашения
                context = {
                    'form': RedeemForm(),  # Новая чистая форма
                    'last_redemption': redemption,
                    'success': True
                }
                return render(request, 'redemptions/redeem_form.html', context)
                
            except ValidationError as e:
                messages.error(request, f'❌ {e.message}')
                return render(request, 'redemptions/redeem_form.html', {'form': form})
    else:
        form = RedeemForm()

    return render(request, 'redemptions/redeem_form.html', {'form': form})

@login_required
def redemption_list(request):
    """Журнал погашений с фильтрами"""
    # Проверка ролей
    if not (request.user.is_superuser or request.user.role in ('cashier', 'manager', 'owner')):
        raise PermissionDenied('Недостаточно прав для просмотра журнала')

    # Базовый queryset
    qs = Redemption.objects.select_related(
        'coupon', 
        'coupon__campaign', 
        'coupon__campaign__business',
        'cashier'
    )

    # Фильтрация по бизнесу (если не superuser)
    if not request.user.is_superuser:
        qs = qs.filter(coupon__campaign__business__owner=request.user)

    # Фильтры из GET параметров
    campaign_id = request.GET.get('campaign')
    if campaign_id:
        qs = qs.filter(coupon__campaign_id=campaign_id)
    
    cashier_id = request.GET.get('cashier')
    if cashier_id:
        qs = qs.filter(cashier_id=cashier_id)
    
    # Поиск по коду купона
    search = request.GET.get('search')
    if search:
        qs = qs.filter(
            Q(coupon__code__icontains=search) |
            Q(pos_ref__icontains=search) |
            Q(note__icontains=search)
        )

    # Пагинация
    paginator = Paginator(qs, 25)
    page = request.GET.get('page')
    page_obj = paginator.get_page(page)

    # Данные для фильтров
    campaigns = Campaign.objects.filter(
        business__owner=request.user if not request.user.is_superuser else None
    ).order_by('name')
    
    context = {
        'page_obj': page_obj,
        'campaigns': campaigns,
        'current_campaign': campaign_id,
        'current_cashier': cashier_id,
        'search_query': search or '',
        'total_count': paginator.count
    }
    
    return render(request, 'redemptions/list.html', context)