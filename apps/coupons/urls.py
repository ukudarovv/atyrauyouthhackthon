from django.urls import path
from . import views

app_name = 'coupons'

urlpatterns = [
    # public - выдача и проверка купонов
    path('l/<slug:slug>/claim/', views.claim, name='claim'),  # форма выдачи купона
    path('c/<str:code>/', views.check, name='check'),         # проверка статуса купона

    # internal - QR и экспорт
    path('l/<slug:slug>/qr.png', views.landing_qr, name='landing_qr'),  # QR-код лендинга
    path('app/coupons/export.csv', views.export_csv, name='export_csv'),  # экспорт CSV
]
