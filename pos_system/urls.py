"""
URL configuration for pos_system project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.accounts.urls')),
    path('', include('apps.businesses.urls')),
    path('', include('apps.campaigns.urls')),
    path('', include('apps.coupons.urls')),
    path('', include('apps.redemptions.urls')),
    path('', include('apps.referrals.urls')),
    path('', include('apps.reviews.urls')),
    path('', include('apps.analytics.urls')),
    path('', include('apps.printing.urls')),
    path('api/ai/', include('apps.ai.urls')),
    path('', include('apps.fraud.urls')),
    path('', include('apps.segments.urls')),
    path('', include('apps.integrations_ig.urls')),
    path('', include('apps.wallet.urls')),
    path('', include('apps.blasts.urls')),
    path('', include('apps.growth.urls')),
    path('', include('apps.nla.urls')),
    path('advisor/', include('apps.advisor.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
