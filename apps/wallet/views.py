from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseBadRequest
from django.contrib import messages
from django.core.paginator import Paginator

from apps.coupons.models import Coupon
from apps.businesses.models import Business
from .models import WalletPass, WalletClass
from .services import (
    create_wallet_pass_for_coupon,
    generate_save_link,
    get_wallet_passes_for_business,
    get_wallet_stats_for_business,
    update_wallet_pass_content
)


@login_required
def wallet_dashboard(request):
    """Главная страница управления Wallet картами"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    business = get_object_or_404(Business, id=biz_id, owner=request.user)
    
    # Получаем статистику
    stats = get_wallet_stats_for_business(business)
    
    # Получаем список карт с пагинацией
    passes = get_wallet_passes_for_business(business)
    paginator = Paginator(passes, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    # Получаем классы карт
    wallet_classes = WalletClass.objects.filter(business=business)
    
    context = {
        'business': business,
        'stats': stats,
        'page_obj': page_obj,
        'wallet_classes': wallet_classes,
    }
    
    return render(request, 'wallet/dashboard.html', context)


@login_required
def create_wallet_pass(request, coupon_id):
    """Создает Wallet карту для купона"""
    coupon = get_object_or_404(Coupon, id=coupon_id, campaign__business__owner=request.user)
    
    # Проверяем, нет ли уже карты для этого купона
    existing_pass = WalletPass.objects.filter(coupon=coupon).first()
    if existing_pass:
        messages.info(request, 'Wallet карта для этого купона уже существует.')
        return redirect('wallet:pass_detail', pk=existing_pass.pk)
    
    # Создаем карту
    wallet_pass = create_wallet_pass_for_coupon(coupon)
    
    if wallet_pass:
        messages.success(request, 'Wallet карта создана успешно!')
        return redirect('wallet:pass_detail', pk=wallet_pass.pk)
    else:
        messages.error(request, 'Не удалось создать Wallet карту. Проверьте настройки Google Wallet.')
        return redirect('/admin/coupons/coupon/{}/change/'.format(coupon_id))


@login_required
def wallet_pass_detail(request, pk):
    """Детали Wallet карты"""
    wallet_pass = get_object_or_404(
        WalletPass, 
        pk=pk, 
        business__owner=request.user
    )
    
    # Генерируем ссылку для сохранения если её нет
    save_link = wallet_pass.metadata.get('save_link')
    if not save_link:
        save_link = generate_save_link(wallet_pass)
    
    context = {
        'wallet_pass': wallet_pass,
        'save_link': save_link,
    }
    
    return render(request, 'wallet/pass_detail.html', context)


@login_required
def generate_save_link_view(request, pk):
    """Генерирует новую ссылку для сохранения в Wallet"""
    if request.method != 'POST':
        return HttpResponseBadRequest('POST required')
    
    wallet_pass = get_object_or_404(
        WalletPass, 
        pk=pk, 
        business__owner=request.user
    )
    
    save_link = generate_save_link(wallet_pass)
    
    if save_link:
        return JsonResponse({
            'success': True,
            'save_link': save_link,
            'message': 'Ссылка сгенерирована успешно'
        })
    else:
        return JsonResponse({
            'success': False,
            'message': 'Не удалось сгенерировать ссылку'
        })


@login_required
def update_wallet_pass_view(request, pk):
    """Обновляет содержимое Wallet карты"""
    if request.method != 'POST':
        return HttpResponseBadRequest('POST required')
    
    wallet_pass = get_object_or_404(
        WalletPass, 
        pk=pk, 
        business__owner=request.user
    )
    
    # Получаем данные для обновления
    title = request.POST.get('title', '').strip()
    subtitle = request.POST.get('subtitle', '').strip()
    message = request.POST.get('message', '').strip()
    
    updates = {}
    
    if title:
        updates['title'] = title
    
    if subtitle:
        updates['subtitle'] = subtitle
    
    if message:
        updates['textModulesData'] = [
            {
                "header": "Сообщение",
                "body": message
            }
        ]
    
    if updates:
        success = update_wallet_pass_content(wallet_pass, updates)
        
        if success:
            messages.success(request, 'Wallet карта обновлена успешно!')
        else:
            messages.error(request, 'Не удалось обновить Wallet карту.')
    else:
        messages.warning(request, 'Нет данных для обновления.')
    
    return redirect('wallet:pass_detail', pk=pk)


@login_required
def wallet_pass_preview(request, pk):
    """Предпросмотр Wallet карты в JSON формате"""
    wallet_pass = get_object_or_404(
        WalletPass, 
        pk=pk, 
        business__owner=request.user
    )
    
    from .gw_client import build_offer_object
    
    try:
        offer_object = build_offer_object(wallet_pass)
        return JsonResponse({
            'success': True,
            'object': offer_object
        }, json_dumps_params={'indent': 2})
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def wallet_settings(request):
    """Настройки Google Wallet"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    business = get_object_or_404(Business, id=biz_id, owner=request.user)
    
    # Проверяем настройки Google Wallet
    gw_configured = all([
        hasattr(settings, 'GOOGLE_WALLET_ISSUER_ID'),
        hasattr(settings, 'GOOGLE_WALLET_SA_KEY_JSON_BASE64'),
    ])
    
    context = {
        'business': business,
        'gw_configured': gw_configured,
        'issuer_id': getattr(settings, 'GOOGLE_WALLET_ISSUER_ID', 'Not configured'),
    }
    
    return render(request, 'wallet/settings.html', context)
