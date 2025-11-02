from django.urls import path
from . import views
from .views_demo import demo_login

app_name = 'advisor'

urlpatterns = [
    path('chat/', views.chat, name='chat'),
    path('new-session/', views.new_session, name='new_session'),
    path('demo-login/', demo_login, name='demo_login'),
    # Экспорт данных
    path('export/analytics/<str:format>/', views.export_analytics, name='export_analytics'),
    path('export/chat/<int:session_id>/<str:format>/', views.export_chat, name='export_chat'),
]
