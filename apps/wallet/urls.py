from django.urls import path
from . import views

app_name = 'wallet'

urlpatterns = [
    path('app/wallet/', views.wallet_dashboard, name='dashboard'),
    path('app/wallet/settings/', views.wallet_settings, name='settings'),
    path('app/wallet/create/<int:coupon_id>/', views.create_wallet_pass, name='create_pass'),
    path('app/wallet/pass/<int:pk>/', views.wallet_pass_detail, name='pass_detail'),
    path('app/wallet/pass/<int:pk>/link/', views.generate_save_link_view, name='generate_link'),
    path('app/wallet/pass/<int:pk>/update/', views.update_wallet_pass_view, name='update_pass'),
    path('app/wallet/pass/<int:pk>/preview/', views.wallet_pass_preview, name='pass_preview'),
]
