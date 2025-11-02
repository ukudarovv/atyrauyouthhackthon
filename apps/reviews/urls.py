from django.urls import path
from . import views

app_name = 'reviews'

urlpatterns = [
    # Публичные маршруты
    path('review/<str:token>/', views.public_form, name='public'),
    path('review/<str:token>/qr.png', views.invite_qr, name='invite_qr'),

    # Внутренние маршруты
    path('app/reviews/', views.list_reviews, name='list'),
    path('app/reviews/<int:pk>/', views.review_detail, name='detail'),
    path('app/reviews/invites/new/', views.invite_new, name='invite_new'),
    path('app/reviews/export.csv', views.export_reviews_csv, name='export_csv'),
]
