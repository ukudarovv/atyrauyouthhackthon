from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, View
from django.http import HttpResponseRedirect

from apps.businesses.mixins import BusinessContextMixin
from apps.businesses.models import Business
from .forms import CampaignForm, LandingForm
from .models import Campaign, Landing, TrackEvent, TrackEventType
from .services import extract_utm, get_client_ip

# ===== Internal (app) =====
class CampaignListView(BusinessContextMixin, ListView):
    model = Campaign
    template_name = 'campaigns/list.html'
    context_object_name = 'campaigns'

    def get_queryset(self):
        qs = super().get_queryset()
        if self.business:
            qs = qs.filter(business=self.business)
        else:
            qs = qs.none()
        return qs.select_related('business', 'location').prefetch_related('events')

class CampaignCreateView(BusinessContextMixin, CreateView):
    model = Campaign
    form_class = CampaignForm
    template_name = 'campaigns/form.html'
    success_url = reverse_lazy('campaigns:list')

    def dispatch(self, request, *args, **kwargs):
        # требуем выбранный бизнес
        if not request.session.get('current_business_id'):
            messages.error(request, 'Сначала выберите или создайте бизнес.')
            return redirect('businesses:list')
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        if self.business:
            initial['business'] = self.business.id
        return initial

    def form_valid(self, form):
        if not self.business or form.cleaned_data['business'] != self.business:
            messages.error(self.request, 'Неверный бизнес. Выберите текущий бизнес.')
            return redirect('businesses:list')
        form.instance.created_by = self.request.user
        resp = super().form_valid(form)
        # создать пустой Landing, если его нет
        Landing.objects.get_or_create(campaign=self.object, defaults={
            'headline': self.object.name,
            'body_md': self.object.description,
        })
        messages.success(self.request, 'Кампания создана.')
        return resp

class CampaignUpdateView(BusinessContextMixin, UpdateView):
    model = Campaign
    form_class = CampaignForm
    template_name = 'campaigns/form.html'
    success_url = reverse_lazy('campaigns:list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_queryset(self):
        return super().get_queryset().filter(business=self.business)

@login_required
def landing_edit(request, pk):
    """Редактирование лендинга кампании"""
    camp = get_object_or_404(Campaign, pk=pk, business__owner=request.user)
    landing, _ = Landing.objects.get_or_create(campaign=camp, defaults={
        'headline': camp.name,
        'body_md': camp.description,
    })
    
    if request.method == 'POST':
        form = LandingForm(request.POST, request.FILES, instance=landing)
        if form.is_valid():
            form.save()
            messages.success(request, 'Лендинг сохранён.')
            return redirect('campaigns:list')
    else:
        form = LandingForm(instance=landing)
    
    return render(request, 'campaigns/form.html', {
        'form': form, 
        'landing_mode': True, 
        'campaign': camp
    })

# ===== Public =====
def landing_public(request, slug: str):
    """Публичная страница лендинга"""
    camp = get_object_or_404(Campaign, slug=slug, is_active=True)
    
    # Записываем событие просмотра
    TrackEvent.objects.create(
        business=camp.business,
        campaign=camp,
        type=TrackEventType.LANDING_VIEW,
        utm=extract_utm(request),
        ip=get_client_ip(request),
        ua=request.META.get('HTTP_USER_AGENT', ''),
        referer=request.META.get('HTTP_REFERER', '')
    )
    
    # Получаем лендинг или создаем дефолтный
    landing = getattr(camp, 'landing', None)
    if not landing:
        landing = Landing.objects.create(
            campaign=camp,
            headline=camp.name,
            body_md=camp.description
        )
    
    ctx = {
        'camp': camp, 
        'landing': landing,
        'query_string': request.META.get('QUERY_STRING', '')
    }
    return render(request, 'public/landing.html', ctx)

def landing_cta_click(request, slug: str):
    """Обработка клика по CTA кнопке"""
    camp = get_object_or_404(Campaign, slug=slug, is_active=True)
    
    # Записываем событие клика
    TrackEvent.objects.create(
        business=camp.business,
        campaign=camp,
        type=TrackEventType.LANDING_CLICK,
        utm=extract_utm(request),
        ip=get_client_ip(request),
        ua=request.META.get('HTTP_USER_AGENT', ''),
        referer=request.META.get('HTTP_REFERER', '')
    )
    
    # Пока просто возвращаем на лендинг; позже тут будет выдача купона
    query_string = request.META.get('QUERY_STRING', '')
    redirect_url = camp.get_public_url()
    if query_string:
        redirect_url += f"?{query_string}"
    
    return HttpResponseRedirect(redirect_url)