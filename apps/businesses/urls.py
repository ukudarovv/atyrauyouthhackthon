from django.urls import path
from . import views

app_name = 'businesses'

urlpatterns = [
    path('app/businesses/', views.BusinessListView.as_view(), name='list'),
    path('app/businesses/new/', views.BusinessCreateView.as_view(), name='create'),
    path('app/businesses/<int:pk>/edit/', views.BusinessUpdateView.as_view(), name='edit'),
    path('app/businesses/<int:pk>/choose/', views.choose_business, name='choose'),

    path('app/locations/', views.LocationListView.as_view(), name='locations'),
    path('app/locations/new/', views.LocationCreateView.as_view(), name='location_create'),
    path('app/locations/<int:pk>/edit/', views.LocationUpdateView.as_view(), name='location_edit'),

    path('app/onboarding/', views.onboarding, name='onboarding'),
]
