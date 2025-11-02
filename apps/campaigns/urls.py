from django.urls import path
from . import views

app_name = 'campaigns'

urlpatterns = [
    # internal (admin panel)
    path('app/campaigns/', views.CampaignListView.as_view(), name='list'),
    path('app/campaigns/new/', views.CampaignCreateView.as_view(), name='create'),
    path('app/campaigns/<int:pk>/edit/', views.CampaignUpdateView.as_view(), name='edit'),
    path('app/campaigns/<int:pk>/landing/', views.landing_edit, name='landing_edit'),

    # public (landing pages)
    path('l/<slug:slug>/', views.landing_public, name='landing_public'),
    path('l/<slug:slug>/cta/', views.landing_cta_click, name='landing_cta'),
]
