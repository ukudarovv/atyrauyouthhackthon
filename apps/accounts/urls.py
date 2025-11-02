from django.urls import path
from . import views

urlpatterns = [
    path('', views.app_home, name='home'),
    path('auth/register/', views.register, name='register'),
    path('auth/login/', views.LoginView.as_view(template_name='accounts/login.html'), name='login'),
    path('auth/logout/', views.LogoutView.as_view(), name='logout'),

    path('auth/password-reset/', views.PasswordResetView.as_view(template_name='accounts/password_reset.html'), name='password_reset'),
    path('auth/password-reset/done/', views.PasswordResetDoneView.as_view(template_name='accounts/password_reset_done.html'), name='password_reset_done'),
    path('auth/reset/<uidb64>/<token>/', views.PasswordResetConfirmView.as_view(template_name='accounts/password_reset_confirm.html'), name='password_reset_confirm'),
    path('auth/reset/done/', views.PasswordResetCompleteView.as_view(template_name='accounts/password_reset_complete.html'), name='password_reset_complete'),
    
    path('auth/set-language/', views.set_language, name='set_language'),
    path('app/', views.app_home, name='app_home'),
]
