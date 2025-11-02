from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpResponseBadRequest
from django.contrib import messages
from django.urls import reverse
from apps.campaigns.models import Campaign
from apps.businesses.models import Business
from .services import qr_data_uri, render_html, render_pdf_from_html, generate_poster_pdf_reportlab, WEASYPRINT_AVAILABLE, REPORTLAB_AVAILABLE


@login_required
def poster_form(request):
    """Форма выбора кампании и размера для печати постера"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    # Получаем кампании текущего бизнеса
    campaigns = Campaign.objects.filter(business_id=biz_id).order_by('-created_at')
    
    # Информируем о доступных режимах генерации PDF
    if WEASYPRINT_AVAILABLE:
        messages.info(request, '✅ Полнофункциональная генерация PDF (WeasyPrint)')
    elif REPORTLAB_AVAILABLE:
        messages.info(request, '📄 Стандартная генерация PDF (ReportLab)')
    else:
        messages.warning(
            request, 
            '⚠️ PDF будет сгенерирован в демонстрационном режиме. '
            'Установите WeasyPrint или ReportLab для полной функциональности.'
        )
    
    return render(request, 'printing/poster_form.html', {
        'campaigns': campaigns,
        'weasyprint_available': WEASYPRINT_AVAILABLE
    })


@login_required 
def poster_pdf(request):
    """Генерация PDF постера"""
    # Получаем параметры
    camp_id = request.GET.get('campaign')
    size = (request.GET.get('size') or 'A4').upper()  # A4|A6
    preview = request.GET.get('preview') == '1'  # HTML превью вместо PDF
    
    # Валидация размера
    if size not in ('A4', 'A6'):
        return HttpResponseBadRequest('Размер должен быть A4 или A6')
    
    # Валидация кампании
    if not camp_id:
        return HttpResponseBadRequest('Не указана кампания')
    
    try:
        camp_id = int(camp_id)
    except (ValueError, TypeError):
        return HttpResponseBadRequest('Некорректный ID кампании')
    
    # Получаем кампанию (проверяем права доступа)
    camp = get_object_or_404(
        Campaign, 
        id=camp_id, 
        business__owner=request.user
    )
    
    # Получаем связанный лендинг
    landing = getattr(camp, 'landing', None)
    
    # Определяем цвет бренда
    brand_color = '#111827'  # Цвет по умолчанию
    if landing and landing.primary_color:
        brand_color = landing.primary_color
    elif hasattr(camp.business, 'brand_color') and camp.business.brand_color:
        brand_color = camp.business.brand_color
    
    # Генерируем публичный URL для QR-кода
    public_url = request.build_absolute_uri(camp.get_public_url())
    
    # Создаем QR-код как data URI
    qr_uri = qr_data_uri(public_url)
    
    # Выбираем шаблон в зависимости от размера
    template_name = 'printing/poster_a4.html' if size == 'A4' else 'printing/poster_a6.html'
    
    # Подготавливаем контекст для шаблона
    context = {
        'camp': camp,
        'landing': landing,
        'qr_uri': qr_uri,
        'brand_color': brand_color,
        'public_url': public_url,
        'is_preview': preview,  # Флаг для превью режима
    }
    
    # Рендерим HTML
    html = render_html(request, template_name, context)
    
    # Если запрошен HTML превью - возвращаем HTML
    if preview:
        return HttpResponse(html, content_type='text/html')
    
    # CSS для правильной печати
    page_css = f"""
    @page {{ 
        size: {size} portrait; 
        margin: 10mm; 
    }}
    * {{ 
        -webkit-print-color-adjust: exact; 
        print-color-adjust: exact; 
    }}
    body {{
        margin: 0;
        padding: 0;
    }}
    """
    
    # Генерируем PDF из HTML (как превью)
    try:
        # Всегда генерируем PDF из HTML для единообразия с превью
        pdf_bytes = render_pdf_from_html(
            html, 
            base_url=request.build_absolute_uri('/'), 
            extra_css=page_css
        )
        
        # Определяем режим генерации для информации
        if WEASYPRINT_AVAILABLE:
            pdf_mode = 'weasyprint-html'
        else:
            pdf_mode = 'mock-html'
            
    except Exception as e:
        return HttpResponseBadRequest(f'Ошибка генерации PDF: {str(e)}')
    
    # Возвращаем PDF файл
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f"poster_{camp.slug}_{size}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Добавляем информацию о режиме работы
    response['X-PDF-Mode'] = pdf_mode
    
    return response


@login_required
def poster_preview(request):
    """HTML превью постера"""
    # Получаем параметры из GET или POST
    camp_id = request.GET.get('campaign') or request.POST.get('campaign')
    size = (request.GET.get('size') or request.POST.get('size') or 'A4').upper()
    
    # Валидация
    if not camp_id:
        return HttpResponseBadRequest('Не указана кампания')
    
    if size not in ('A4', 'A6'):
        return HttpResponseBadRequest('Размер должен быть A4 или A6')
    
    try:
        camp_id = int(camp_id)
    except (ValueError, TypeError):
        return HttpResponseBadRequest('Некорректный ID кампании')
    
    # Получаем кампанию
    camp = get_object_or_404(
        Campaign, 
        id=camp_id, 
        business__owner=request.user
    )
    
    # Получаем связанный лендинг
    landing = getattr(camp, 'landing', None)
    
    # Определяем цвет бренда
    brand_color = '#111827'
    if landing and landing.primary_color:
        brand_color = landing.primary_color
    elif hasattr(camp.business, 'brand_color') and camp.business.brand_color:
        brand_color = camp.business.brand_color
    
    # Генерируем публичный URL для QR-кода
    public_url = request.build_absolute_uri(camp.get_public_url())
    
    # Создаем QR-код как data URI
    qr_uri = qr_data_uri(public_url)
    
    # Выбираем шаблон
    template_name = 'printing/poster_a4.html' if size == 'A4' else 'printing/poster_a6.html'
    
    # Подготавливаем контекст
    context = {
        'camp': camp,
        'landing': landing,
        'qr_uri': qr_uri,
        'brand_color': brand_color,
        'public_url': public_url,
        'is_preview': True,
    }
    
    # Рендерим HTML
    html = render_html(request, template_name, context)
    
    # Возвращаем HTML превью
    return HttpResponse(html, content_type='text/html')