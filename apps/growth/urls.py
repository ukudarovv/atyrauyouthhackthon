from django.urls import path
from . import views

app_name = 'growth'

urlpatterns = [
    # Mystery Drop
    path('mystery/<slug:campaign_slug>/', views.mystery_drop_landing, name='mystery_landing'),
    path('api/mystery/<int:mystery_drop_id>/attempt/', views.mystery_drop_attempt, name='mystery_attempt'),
    
    # Power Hour
    path('app/growth/power-hours/', views.power_hour_list, name='power_hour_list'),
    path('app/growth/power-hours/create/', views.power_hour_create, name='power_hour_create'),
    path('app/growth/power-hours/<int:pk>/', views.power_hour_detail, name='power_hour_detail'),
    path('app/growth/power-hours/<int:pk>/start/', views.power_hour_start, name='power_hour_start'),
    path('app/growth/power-hours/<int:pk>/cancel/', views.power_hour_cancel, name='power_hour_cancel'),
    
    # Mystery Drop Admin
    path('app/growth/mystery-drops/', views.mystery_drop_list, name='mystery_drop_list'),
    path('app/growth/mystery-drops/create/', views.mystery_drop_create, name='mystery_drop_create'),
    path('app/growth/mystery-drops/<int:pk>/', views.mystery_drop_detail, name='mystery_drop_detail'),
    # path('app/growth/mystery-drops/<int:pk>/edit/', views.mystery_drop_edit, name='mystery_drop_edit'),
    
    # Analytics
    path('app/growth/analytics/', views.growth_analytics, name='analytics'),
    
    # Streaks
    path('app/growth/streaks/', views.streaks_overview, name='streaks_overview'),
]
