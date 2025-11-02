from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    path('app/analytics/', views.dashboard, name='dashboard'),
    path('app/analytics/_cards', views.cards_partial, name='cards_partial'),
    path('app/analytics/_series', views.series_partial, name='series_partial'),
    path('app/analytics/_top', views.top_campaigns_partial, name='top_campaigns_partial'),
]
