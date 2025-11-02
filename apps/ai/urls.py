from django.urls import path
from . import views

app_name = 'ai'

urlpatterns = [
    path('campaigns/<int:campaign_id>/copywriting/start/', views.start_copywriting, name='start_copywriting'),
    path('campaigns/<int:campaign_id>/copywriting/apply/', views.apply_copywriting, name='apply_copywriting'),
    path('jobs/<int:job_id>/status/', views.job_status, name='job_status'),
]
