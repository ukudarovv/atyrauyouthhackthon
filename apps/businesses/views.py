from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView

from .forms import BusinessForm, LocationForm
from .models import Business, Location
from .mixins import OwnerQuerysetMixin, BusinessContextMixin

# ====== Бизнесы ======
class BusinessListView(OwnerQuerysetMixin, ListView):
    model = Business
    template_name = 'businesses/business_list.html'
    context_object_name = 'businesses'

class BusinessCreateView(LoginRequiredMixin, CreateView):
    model = Business
    form_class = BusinessForm
    template_name = 'businesses/business_form.html'
    success_url = reverse_lazy('businesses:list')

    def form_valid(self, form):
        form.instance.owner = self.request.user
        resp = super().form_valid(form)
        # После создания делаем его активным
        self.request.session['current_business_id'] = self.object.id
        messages.success(self.request, 'Бизнес создан и выбран активным.')
        return resp

class BusinessUpdateView(OwnerQuerysetMixin, UpdateView):
    model = Business
    form_class = BusinessForm
    template_name = 'businesses/business_form.html'
    success_url = reverse_lazy('businesses:list')

@login_required
def choose_business(request, pk):
    biz = get_object_or_404(Business, pk=pk, owner=request.user)
    request.session['current_business_id'] = biz.id
    messages.success(request, f'Текущий бизнес: {biz.name}')
    return redirect('businesses:list')

# ====== Локации ======
class LocationListView(BusinessContextMixin, ListView):
    model = Location
    template_name = 'businesses/location_list.html'
    context_object_name = 'locations'

    def get_queryset(self):
        qs = super().get_queryset()
        if self.business:
            qs = qs.filter(business=self.business)
        else:
            qs = qs.none()
        return qs

class LocationCreateView(BusinessContextMixin, CreateView):
    model = Location
    form_class = LocationForm
    template_name = 'businesses/location_form.html'
    success_url = reverse_lazy('businesses:locations')

    def dispatch(self, request, *args, **kwargs):
        # требуем выбранный бизнес
        if not request.session.get('current_business_id'):
            messages.error(request, 'Сначала выберите или создайте бизнес.')
            return redirect('businesses:list')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.business_id = self.request.session['current_business_id']
        messages.success(self.request, 'Локация создана.')
        return super().form_valid(form)

class LocationUpdateView(BusinessContextMixin, UpdateView):
    model = Location
    form_class = LocationForm
    template_name = 'businesses/location_form.html'
    success_url = reverse_lazy('businesses:locations')

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(business_id=self.request.session.get('current_business_id'))

# ====== Онбординг ======
@login_required
def onboarding(request):
    """
    Шаг 1: если нет бизнесов — форма Business
    Шаг 2: если нет локаций у выбранного бизнеса — форма Location
    Иначе — редирект на дашборд (/app/)
    """
    # если есть текущий бизнес - используем его, иначе берем первый
    biz_id = request.session.get('current_business_id')
    biz = None
    if not biz_id:
        biz = Business.objects.filter(owner=request.user).first()
        if biz:
            request.session['current_business_id'] = biz.id
    else:
        biz = Business.objects.filter(id=biz_id, owner=request.user).first()

    # Шаг 1: создать бизнес
    if not biz:
        if request.method == 'POST':
            bform = BusinessForm(request.POST)
            if bform.is_valid():
                b = bform.save(commit=False)
                b.owner = request.user
                b.save()
                request.session['current_business_id'] = b.id
                messages.success(request, 'Бизнес создан.')
                return redirect('businesses:onboarding')
        else:
            bform = BusinessForm()
        return render(request, 'businesses/onboarding.html', {'step': 1, 'business_form': bform})

    # Шаг 2: создать первую локацию
    if not biz.locations.exists():
        if request.method == 'POST':
            lform = LocationForm(request.POST)
            if lform.is_valid():
                loc = lform.save(commit=False)
                loc.business = biz
                loc.save()
                messages.success(request, 'Первая локация создана.')
                return redirect('/app/')
        else:
            lform = LocationForm()
        return render(request, 'businesses/onboarding.html', {'step': 2, 'location_form': lform, 'business': biz})

    # Готово
    return redirect('/app/')