from django.apps import AppConfig


class GrowthConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.growth'
    verbose_name = 'Growth Hacking'
    
    def ready(self):
        from . import signals  # noqa
