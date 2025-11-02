from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.http import HttpResponseRedirect
from django.views.decorators.http import require_POST
from .forms import RegisterForm

def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Аккаунт создан')
            return redirect('businesses:onboarding')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})

# Готовые CBV для аутентификации
LoginView = auth_views.LoginView
LogoutView = auth_views.LogoutView
PasswordResetView = auth_views.PasswordResetView
PasswordResetDoneView = auth_views.PasswordResetDoneView
PasswordResetConfirmView = auth_views.PasswordResetConfirmView
PasswordResetCompleteView = auth_views.PasswordResetCompleteView

@require_POST
def set_language(request):
    lang = request.POST.get('lang', 'ru')
    request.session['lang'] = lang
    if request.user.is_authenticated:
        request.user.locale = lang
        request.user.save(update_fields=['locale'])
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

@login_required
def app_home(request):
    # Получаем статистику для отображения на главной странице
    context = {}
    
    try:
        from apps.campaigns.models import Campaign
        from apps.coupons.models import Coupon
        from apps.redemptions.models import Redemption
        from apps.customers.models import Customer
        from apps.advisor.dashboard_widgets import DashboardWidgets
        
        # Если пользователь владелец, показываем статистику его бизнеса
        if hasattr(request.user, 'businesses') and request.user.businesses.exists():
            business = request.user.businesses.first()
            
            # Основная статистика
            context.update({
                'total_campaigns': Campaign.objects.filter(business=business).count(),
                'total_coupons': Coupon.objects.filter(campaign__business=business).count(),
                'total_redemptions': Redemption.objects.filter(coupon__campaign__business=business).count(),
                'total_customers': Customer.objects.filter(business=business).count(),
            })
            
            # Интерактивные виджеты
            widgets = DashboardWidgets(business)
            context.update({
                'live_metrics': widgets.get_live_metrics(),
                'hourly_chart': widgets.get_hourly_activity_chart(),
                'weekly_chart': widgets.get_weekly_trend_chart(),
                'top_campaigns_chart': widgets.get_top_campaigns_widget(),
                'quick_actions': widgets.get_quick_actions(),
                'performance_score': widgets.get_performance_score(),
                'recent_activity': widgets.get_recent_activity(),
            })
        else:
            # Общая статистика для менеджеров/кассиров
            context.update({
                'total_campaigns': Campaign.objects.count(),
                'total_coupons': Coupon.objects.count(),
                'total_redemptions': Redemption.objects.count(),
                'total_customers': Customer.objects.count(),
            })
    except Exception as e:
        # Если модели не загружены или ошибка, показываем нули
        print(f"Error loading dashboard data: {e}")
        context.update({
            'total_campaigns': 0,
            'total_coupons': 0,
            'total_redemptions': 0,
            'total_customers': 0,
        })
    
    return render(request, 'accounts/app_home.html', context)