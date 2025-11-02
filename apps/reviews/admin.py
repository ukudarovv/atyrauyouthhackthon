from django.contrib import admin
from .models import Review, ReviewInvite

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('business', 'rating', 'ai_sentiment', 'ai_toxic', 'is_published', 'created_at')
    list_filter = ('business', 'is_published', 'ai_toxic', 'rating', 'created_at')
    search_fields = ('text', 'phone', 'email', 'ai_summary')
    readonly_fields = ('created_at', 'ai_sentiment', 'ai_labels', 'ai_toxic', 'ai_summary')
    
    fieldsets = (
        (None, {
            'fields': ('business', 'campaign', 'rating', 'text', 'phone', 'email')
        }),
        ('Публикация', {
            'fields': ('publish_consent', 'is_published')
        }),
        ('AI Анализ', {
            'fields': ('ai_sentiment', 'ai_labels', 'ai_toxic', 'ai_summary'),
            'classes': ('collapse',)
        }),
        ('Метаданные', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('business', 'campaign')

@admin.register(ReviewInvite)
class ReviewInviteAdmin(admin.ModelAdmin):
    list_display = ('business','campaign','token','source','created_at','used_at','expires_at')
    list_filter = ('business','source','created_at')
    search_fields = ('token','phone','email')
    readonly_fields = ('created_at',)