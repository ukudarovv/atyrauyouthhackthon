from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
import csv
import qrcode
from io import BytesIO

from apps.campaigns.models import Campaign, TrackEvent, TrackEventType
from apps.campaigns.services import get_client_ip, extract_utm
from apps.referrals.services import get_or_create_customer, attach_referral_if_present
from apps.referrals.models import CustomerSource
from apps.fraud.services import score_issue
from apps.fraud.models import RiskDecision
from .forms import ClaimForm
from .models import Coupon, CouponStatus
from .services import can_issue_for_phone, issue_coupon

# ===== PUBLIC: форма выдачи купона по кампании =====
def claim(request, slug: str):
    """Форма выдачи купона для кампании"""
    camp = get_object_or_404(Campaign, slug=slug, is_active=True)
    
    # Проверяем что кампания активна
    if not camp.is_running_now():
        messages.error(request, 'Акция недоступна или завершена.')
        return redirect('campaigns:landing_public', slug=slug)

    # Проверяем общий лимит
    if camp.remaining() <= 0:
        messages.error(request, 'Все купоны уже выданы.')
        return redirect('campaigns:landing_public', slug=slug)

    if request.method == 'POST':
        form = ClaimForm(request.POST)
        if form.is_valid():
            phone = form.cleaned_data['phone']
            
            # Проверяем лимит для номера телефона
            if not can_issue_for_phone(camp, phone):
                messages.error(request, f'На этот номер уже выдано максимальное количество купонов ({camp.per_phone_limit}).')
                return render(request, 'coupons/claim_form.html', {'camp': camp, 'form': form})

            # АНТИФРОД: скоринг до выдачи
            score, reasons, decision = score_issue(request, campaign=camp, phone=phone)
            
            if decision == RiskDecision.BLOCK:
                messages.error(request, 'Не удалось выдать купон. Попробуйте позже или обратитесь в поддержку.')
                return redirect('campaigns:landing_public', slug=slug)

            try:
                # Срок действия = конец кампании (если указан)
                expires_at = camp.ends_at

                # Выдаем купон
                coupon = issue_coupon(camp, phone, expires_at=expires_at)

                # Сохраняем метаданные и риск
                coupon.risk_score = score
                coupon.risk_flag = (decision != RiskDecision.ALLOW)
                coupon.metadata = {
                    "ip": request.META.get('HTTP_X_FORWARDED_FOR','').split(',')[0].strip() or request.META.get('REMOTE_ADDR'),
                    "ua": request.META.get('HTTP_USER_AGENT',''),
                    "utm": {
                        k: request.GET.get(k) or request.POST.get(k)
                        for k in ["utm_source","utm_medium","utm_campaign","utm_term","utm_content"] 
                        if (request.GET.get(k) or request.POST.get(k))
                    }
                }
                coupon.save(update_fields=['risk_score','risk_flag','metadata'])

                # NEW: создаём/находим клиента и привязываем реферала если есть
                customer = get_or_create_customer(
                    business=camp.business,
                    phone=phone,
                    source=CustomerSource.LANDING
                )
                attach_referral_if_present(request, business=camp.business, referee_customer=customer)

                # Записываем событие аналитики
                TrackEvent.objects.create(
                    business=camp.business,
                    campaign=camp,
                    type=TrackEventType.COUPON_ISSUE,
                    utm=extract_utm(request),
                    ip=get_client_ip(request),
                    ua=request.META.get('HTTP_USER_AGENT', ''),
                    referer=request.META.get('HTTP_REFERER', '')
                )

                return render(request, 'coupons/claim_success.html', {'camp': camp, 'coupon': coupon})
            
            except ValueError as e:
                messages.error(request, str(e))
                return render(request, 'coupons/claim_form.html', {'camp': camp, 'form': form})
    else:
        form = ClaimForm()

    # Добавляем информацию о лимитах в контекст
    context = {
        'camp': camp, 
        'form': form,
        'remaining': camp.remaining(),
        'issued_count': camp.issued_count()
    }
    return render(request, 'coupons/claim_form.html', context)

# ===== PUBLIC: проверка статуса купона =====
def check(request, code: str):
    """Проверка статуса купона по коду"""
    coupon = get_object_or_404(Coupon, code=code.upper())
    
    # Определяем статус для отображения
    if coupon.is_active():
        status_text = 'Действителен'
        status_class = 'text-green-600'
    elif coupon.status == CouponStatus.REDEEMED:
        status_text = 'Погашен'
        status_class = 'text-red-600'
    elif coupon.is_expired():
        status_text = 'Истек срок действия'
        status_class = 'text-yellow-600'
    else:
        status_text = 'Недействителен'
        status_class = 'text-gray-600'

    context = {
        'coupon': coupon, 
        'status_text': status_text,
        'status_class': status_class
    }
    return render(request, 'coupons/check.html', context)

# ===== INTERNAL: QR PNG для лендинга =====
def landing_qr(request, slug: str):
    """Генерирует QR-код для лендинга"""
    camp = get_object_or_404(Campaign, slug=slug)
    
    # URL лендинга
    url = request.build_absolute_uri(reverse('campaigns:landing_public', args=[slug]))
    
    # Генерируем QR-код
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    # Создаем изображение
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Возвращаем как PNG
    buf = BytesIO()
    img.save(buf, format='PNG')
    
    response = HttpResponse(buf.getvalue(), content_type='image/png')
    response['Cache-Control'] = 'public, max-age=3600'  # Кэшируем на час
    return response

# ===== INTERNAL: экспорт CSV =====
@login_required
def export_csv(request):
    """Экспорт купонов в CSV формате"""
    camp_id = request.GET.get('campaign')
    
    # Фильтруем купоны
    qs = Coupon.objects.select_related('campaign', 'campaign__business')
    
    # Ограничиваем доступ только к купонам пользователя
    if request.user.is_superuser:
        # Суперпользователь видит все
        pass
    else:
        # Обычный пользователь видит только свои бизнесы
        qs = qs.filter(campaign__business__owner=request.user)
    
    if camp_id:
        qs = qs.filter(campaign_id=camp_id)

    # Формируем CSV
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="coupons.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Код', 'Кампания', 'Бизнес', 'Телефон', 'Выдан', 
        'Истекает', 'Статус', 'Использований', 'Макс. использований'
    ])
    
    for c in qs.order_by('-issued_at'):
        writer.writerow([
            c.code,
            c.campaign.name,
            c.campaign.business.name,
            c.phone,
            c.issued_at.strftime('%d.%m.%Y %H:%M'),
            c.expires_at.strftime('%d.%m.%Y %H:%M') if c.expires_at else '',
            c.get_status_display(),
            c.uses_count,
            c.max_uses
        ])
    
    return response