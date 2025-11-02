from django.urls import path
from . import views

app_name = 'nla'

urlpatterns = [
    path('app/analytics/ask/', views.ask, name='ask'),
    path('app/analytics/ask/csv/', views.ask_csv, name='ask_csv'),
    path('chat/', views.ask, name='chat'),  # Для advisor:chat URL
]
