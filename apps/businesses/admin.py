from django.contrib import admin
from .models import Business, Location

@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'owner', 'phone', 'created_at')
    search_fields = ('name', 'owner__username', 'phone')
    list_filter = ('timezone',)
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'business', 'is_active')
    search_fields = ('name', 'business__name', 'address')
    list_filter = ('is_active',)