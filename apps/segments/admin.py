from django.contrib import admin
from .models import Segment, SegmentMember


@admin.register(Segment)
class SegmentAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'business', 'kind', 'size_cached', 'enabled', 
        'last_built_at', 'is_stale'
    )
    list_filter = ('business', 'kind', 'enabled', 'created_at')
    search_fields = ('name', 'business__name', 'description')
    readonly_fields = (
        'size_cached', 'preview', 'last_built_at', 'is_stale',
        'created_at', 'updated_at'
    )
    
    fieldsets = (
        (None, {
            'fields': ('business', 'name', 'slug', 'kind', 'enabled')
        }),
        ('Настройки', {
            'fields': ('description', 'color', 'is_dynamic', 'definition')
        }),
        ('Статистика', {
            'fields': ('size_cached', 'preview', 'last_built_at', 'is_stale'),
            'classes': ('collapse',)
        }),
        ('Метаданные', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('business')


@admin.register(SegmentMember)
class SegmentMemberAdmin(admin.ModelAdmin):
    list_display = ('segment', 'customer', 'added_at')
    list_filter = ('segment__business', 'segment', 'added_at')
    search_fields = ('customer__phone_e164', 'segment__name')
    raw_id_fields = ('segment', 'customer')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'segment', 'segment__business', 'customer'
        )
