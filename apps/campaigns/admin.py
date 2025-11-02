from django.contrib import admin
from .models import Campaign, Landing, TrackEvent

@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'business', 'type', 'is_active', 'starts_at', 'ends_at')
    search_fields = ('name', 'business__name', 'slug')
    list_filter = ('type', 'is_active', 'business')
    prepopulated_fields = {'slug': ('name',)}
    date_hierarchy = 'created_at'

@admin.register(Landing)
class LandingAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'headline', 'primary_color')
    search_fields = ('campaign__name', 'headline')

@admin.register(TrackEvent)
class TrackEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', 'campaign', 'ip', 'created_at')
    list_filter = ('type', 'campaign', 'business')
    search_fields = ('referer', 'ip')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)