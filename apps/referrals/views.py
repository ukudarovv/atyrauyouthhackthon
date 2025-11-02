from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.core.paginator import Paginator
from apps.campaigns.models import Campaign, TrackEvent, TrackEventType
from apps.businesses.models import Business
from .models import Referral, Customer
from .forms import CustomerForm
from .services import create_referral_for_referrer

def referral_entry(request, token):
    ref = get_object_or_404(Referral, token=token)
    # Аналитика клика
    TrackEvent.objects.create(
        business=ref.business,
        campaign=None,
        type=TrackEventType.REFERRAL_CLICK,
        utm={}, ip=request.META.get('REMOTE_ADDR'),
        ua=request.META.get('HTTP_USER_AGENT',''),
        referer=request.META.get('HTTP_REFERER','')
    )
    # Сохраняем токен в сессию для последующей выдачи купона
    request.session['ref_token'] = token

    # На какую кампанию вести? Берём первую активную бизнес-кампанию
    camp = Campaign.objects.filter(business=ref.business, is_active=True).order_by('-id').first()
    if camp:
        return redirect(camp.get_public_url())
    # Фолбэк: простая страница с сообщением
    return render(request, 'referrals/public/referral_entry.html', {'ref': ref})

@login_required
def customers_list(request):
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    qs = Customer.objects.filter(business_id=biz_id).order_by('-id')
    page_obj = Paginator(qs, 20).get_page(request.GET.get('page'))
    return render(request, 'referrals/list.html', {'page_obj': page_obj})

@login_required
def customer_create(request):
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            c = form.save(commit=False)
            c.business_id = biz_id
            c.save()
            messages.success(request, 'Клиент создан.')
            return redirect('referrals:customers')
    else:
        form = CustomerForm()
    return render(request, 'referrals/customer_form.html', {'form': form})

@login_required
def referral_new(request, customer_id):
    cust = get_object_or_404(Customer, id=customer_id, business__owner=request.user)
    ref = create_referral_for_referrer(business=cust.business, referrer_customer=cust)
    messages.success(request, f'Реферальная ссылка создана: /r/{ref.token}/')
    return redirect('referrals:customers')