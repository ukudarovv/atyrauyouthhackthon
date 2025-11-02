from django.urls import path
from . import views

app_name = 'printing'

urlpatterns = [
    path('app/print/', views.poster_form, name='form'),
    path('app/print/pdf/', views.poster_pdf, name='pdf'),
    path('app/print/preview/', views.poster_preview, name='preview'),
]
