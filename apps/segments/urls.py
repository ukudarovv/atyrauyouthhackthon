from django.urls import path
from . import views

app_name = 'segments'

urlpatterns = [
    path('app/segments/', views.seg_list, name='list'),
    path('app/segments/new/', views.seg_edit, name='new'),
    path('app/segments/<int:pk>/', views.seg_edit, name='edit'),
    path('app/segments/<int:pk>/preview/', views.seg_preview, name='preview'),
    path('app/segments/<int:pk>/rebuild/', views.seg_rebuild, name='rebuild'),
    path('app/segments/<int:pk>/insights/', views.seg_insights, name='insights'),
]
