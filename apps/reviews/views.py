from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponse
from django.urls import reverse
from django.core.paginator import Paginator
from django.db import models
import qrcode
import csv
from io import BytesIO

from .models import Review, ReviewInvite
from .forms import PublicReviewForm
from .services import external_links_from_business, create_invite
from apps.campaigns.models import TrackEvent, TrackEventType, Campaign
from apps.businesses.models import Business

# ===== PUBLIC VIEWS =====

def public_form(request, token: str):
    """Публичная форма отзыва"""
    inv = get_object_or_404(ReviewInvite, token=token)
    if not inv.is_valid():
        return render(request, 'public/review_form.html', {'invalid': True, 'invite': inv})

    if request.method == 'POST':
        form = PublicReviewForm(request.POST)
        if form.is_valid():
            r = form.save(commit=False)
            r.business = inv.business
            r.campaign = inv.campaign
            r.phone = inv.phone
            r.email = inv.email
            r.save()

            # Помечаем инвайт использованным
            inv.used_at = timezone.now()
            inv.save(update_fields=['used_at'])

            # Записываем аналитику
            TrackEvent.objects.create(
                business=inv.business,
                campaign=inv.campaign,
                type=TrackEventType.REVIEW_SUBMIT,
                utm={}, 
                ip=request.META.get('REMOTE_ADDR'),
                ua=request.META.get('HTTP_USER_AGENT',''),
                referer=request.META.get('HTTP_REFERER','')
            )

            # Показываем страницу благодарности с deeplinks
            links = external_links_from_business(inv.business)
            return render(request, 'public/review_thanks.html', {
                'review': r, 
                'links': links,
                'business': inv.business
            })
    else:
        form = PublicReviewForm()

    return render(request, 'public/review_form.html', {
        'invite': inv, 
        'form': form,
        'business': inv.business
    })

def invite_qr(request, token: str):
    """QR-код для приглашения на отзыв"""
    inv = get_object_or_404(ReviewInvite, token=token)
    url = request.build_absolute_uri(reverse('reviews:public', args=[token]))
    
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

# ===== INTERNAL VIEWS =====

@login_required
def list_reviews(request):
    """Список отзывов"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    qs = Review.objects.filter(business_id=biz_id).select_related('campaign')
    
    # Фильтрация
    rating = request.GET.get('rating')
    if rating:
        qs = qs.filter(rating=rating)
    
    published = request.GET.get('published')
    if published == '1':
        qs = qs.filter(is_published=True)
    elif published == '0':
        qs = qs.filter(is_published=False)
    
    page_obj = Paginator(qs, 20).get_page(request.GET.get('page'))
    
    # Статистика
    stats = {
        'total': Review.objects.filter(business_id=biz_id).count(),
        'published': Review.objects.filter(business_id=biz_id, is_published=True).count(),
        'avg_rating': Review.objects.filter(business_id=biz_id).aggregate(
            avg=models.Avg('rating')
        )['avg'] or 0
    }
    
    return render(request, 'reviews/list.html', {
        'page_obj': page_obj,
        'stats': stats,
        'current_rating': rating,
        'current_published': published
    })

@login_required
def review_detail(request, pk: int):
    """Детали отзыва"""
    r = get_object_or_404(Review, pk=pk, business__owner=request.user)
    
    if request.method == 'POST':
        # Переключение публикации
        r.is_published = not r.is_published
        r.save(update_fields=['is_published'])
        status = 'опубликован' if r.is_published else 'скрыт'
        messages.success(request, f'Отзыв {status}.')
        return redirect('reviews:list')
    
    return render(request, 'reviews/detail.html', {'review': r})

@login_required
def invite_new(request):
    """Создание нового приглашения на отзыв"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    biz = get_object_or_404(Business, id=biz_id, owner=request.user)

    if request.method == 'POST':
        phone = request.POST.get('phone','').strip()
        email = request.POST.get('email','').strip()
        campaign_id = request.POST.get('campaign') or None
        ttl_hours = int(request.POST.get('ttl_hours', 72))
        
        campaign = None
        if campaign_id:
            campaign = Campaign.objects.filter(id=campaign_id, business=biz).first()
        
        inv = create_invite(
            business=biz, 
            campaign=campaign, 
            phone=phone, 
            email=email,
            ttl_hours=ttl_hours
        )
        
        review_url = request.build_absolute_uri(reverse('reviews:public', args=[inv.token]))
        qr_url = request.build_absolute_uri(reverse('reviews:invite_qr', args=[inv.token]))
        
        messages.success(request, f'Ссылка для отзыва создана: {review_url}')
        return redirect('reviews:list')

    # Получаем кампании для выбора
    campaigns = Campaign.objects.filter(business=biz).order_by('-created_at')[:10]
    return render(request, 'reviews/invite_form.html', {'campaigns': campaigns})

@login_required
def export_reviews_csv(request):
    """Экспорт отзывов в CSV"""
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        messages.error(request, 'Сначала выберите бизнес.')
        return redirect('businesses:list')
    
    qs = Review.objects.filter(business_id=biz_id).select_related('campaign')
    
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="reviews.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Дата', 'Рейтинг', 'Текст', 'Опубликован', 
        'Телефон', 'Email', 'Кампания', 'Согласие на публикацию'
    ])
    
    for r in qs.order_by('-created_at'):
        writer.writerow([
            r.created_at.strftime('%d.%m.%Y %H:%M'),
            r.rating,
            r.text,
            'Да' if r.is_published else 'Нет',
            r.phone,
            r.email,
            r.campaign.name if r.campaign else '',
            'Да' if r.publish_consent else 'Нет'
        ])
    
    return response