from django.contrib import admin
from .models import AIJob

@admin.register(AIJob)
class AIJobAdmin(admin.ModelAdmin):
    list_display = ('job_type', 'status', 'user', 'campaign', 'created_at', 'completed_at')
    list_filter = ('job_type', 'status', 'created_at')
    search_fields = ('user__username', 'campaign__name')
    readonly_fields = ('created_at', 'started_at', 'completed_at')
    
    fieldsets = (
        (None, {
            'fields': ('user', 'campaign', 'job_type', 'status')
        }),
        ('Data', {
            'fields': ('input_data', 'output_data', 'error_message'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'started_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )
