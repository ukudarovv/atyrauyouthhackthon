from django.urls import path
from . import views

app_name = 'blasts'

urlpatterns = [
    # Главная страница рассылок
    path('app/blasts/', views.blast_list, name='list'),
    path('app/blasts/create/', views.blast_create, name='create'),
    path('app/blasts/<int:pk>/', views.blast_detail, name='detail'),
    path('app/blasts/<int:pk>/edit/', views.blast_edit, name='edit'),
    
    # Управление рассылками
    path('app/blasts/<int:pk>/start/', views.blast_start, name='start'),
    path('app/blasts/<int:pk>/pause/', views.blast_pause, name='pause'),
    path('app/blasts/<int:pk>/resume/', views.blast_resume, name='resume'),
    path('app/blasts/<int:pk>/cancel/', views.blast_cancel, name='cancel'),
    
    # Аналитика
    path('app/blasts/<int:pk>/analytics/', views.blast_analytics, name='analytics'),
    path('app/blasts/<int:pk>/export/', views.blast_export, name='export'),
    
    # Шаблоны сообщений
    path('app/templates/', views.template_list, name='template_list'),
    path('app/templates/create/', views.template_create, name='template_create'),
    path('app/templates/<int:pk>/', views.template_detail, name='template_detail'),
    path('app/templates/<int:pk>/edit/', views.template_edit, name='template_edit'),
    
    # Контактные точки
    path('app/contacts/', views.contact_point_list, name='contact_list'),
    path('app/contacts/sync/', views.contact_sync, name='contact_sync'),
    
    # Короткие ссылки
    path('s/<str:short_code>/', views.short_link_redirect, name='short_redirect'),
    
    # Webhooks
    path('webhooks/delivery/', views.delivery_webhook, name='delivery_webhook'),
    path('webhooks/sendgrid/', views.sendgrid_webhook, name='sendgrid_webhook'),
    path('webhooks/twilio/', views.twilio_webhook, name='twilio_webhook'),
    path('webhooks/infobip/', views.infobip_webhook, name='infobip_webhook'),
    path('webhooks/whatsapp/', views.whatsapp_webhook, name='whatsapp_webhook'),
    path('webhooks/generic/', views.generic_delivery_webhook, name='generic_webhook'),
]
