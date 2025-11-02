from django.contrib import admin
from .models import AdvisorSession, AdvisorMessage

@admin.register(AdvisorSession)
class AdvisorSessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'business', 'is_active', 'created_at', 'updated_at']
    list_filter = ['is_active', 'created_at', 'business']
    search_fields = ['user__username', 'business__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'business')

@admin.register(AdvisorMessage)
class AdvisorMessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'session_user', 'session_business', 'role', 'content_preview', 'created_at']
    list_filter = ['role', 'created_at', 'session__business']
    search_fields = ['session__user__username', 'session__business__name', 'content__text']
    readonly_fields = ['id', 'created_at']
    
    def session_user(self, obj):
        return obj.session.user.username
    session_user.short_description = 'Пользователь'
    
    def session_business(self, obj):
        return obj.session.business.name
    session_business.short_description = 'Бизнес'
    
    def content_preview(self, obj):
        text = obj.content.get('text', '')
        return text[:100] + '...' if len(text) > 100 else text
    content_preview.short_description = 'Содержимое'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('session__user', 'session__business')
