from django.apps import AppConfig


class IntegrationsIgConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.integrations_ig'
    verbose_name = 'Instagram Integration'
    
    def ready(self):
        try:
            from . import signals  # noqa
        except ImportError:
            pass
