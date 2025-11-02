from django.urls import path
from . import views

app_name = 'fraud'

urlpatterns = [
    path('app/fraud/', views.risk_list, name='list'),
    path('app/fraud/<int:pk>/resolve/', views.risk_resolve, name='resolve'),
    path('app/fraud/denies/add/', views.denies_add, name='denies_add'),
]
