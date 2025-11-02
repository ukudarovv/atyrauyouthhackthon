from django.urls import path
from . import views

app_name = 'redemptions'

urlpatterns = [
    path('app/redemptions/redeem/', views.redeem_view, name='redeem'),
    path('app/redemptions/', views.redemption_list, name='list'),
]
