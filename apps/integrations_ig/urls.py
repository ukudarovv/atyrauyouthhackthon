"""
URL маршруты для Instagram интеграции
"""
from django.urls import path
from . import views

app_name = 'integrations_ig'

urlpatterns = [
    # OAuth флоу
    path('app/instagram/connect/', views.connect_instagram, name='connect'),
    path('app/instagram/callback/', views.oauth_callback, name='callback'),
    path('app/instagram/select-account/', views.select_account, name='select_account'),
    
    # Основные страницы
    path('app/instagram/', views.dashboard, name='dashboard'),
    path('app/instagram/media/', views.media_library, name='media_library'),
    path('app/instagram/media/<int:media_id>/', views.media_detail, name='media_detail'),
    
    # API endpoints
    path('api/instagram/media/<int:media_id>/publish/', views.publish_media, name='publish_media'),
    
    # Webhooks
    path('integrations/ig/webhook/', views.webhook_endpoint, name='webhook'),
]
