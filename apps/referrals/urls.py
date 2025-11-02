from django.urls import path
from . import views

app_name = 'referrals'

urlpatterns = [
    # Публичные маршруты
    path('r/<str:token>/', views.referral_entry, name='referral_entry'),
    
    # Внутренние маршруты
    path('app/customers/', views.customers_list, name='customers'),
    path('app/customers/new/', views.customer_create, name='customer_create'),
    path('app/customers/<int:customer_id>/referral/new/', views.referral_new, name='referral_new'),
]
