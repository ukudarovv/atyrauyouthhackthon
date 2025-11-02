from django.utils import translation

class LocalePreferenceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        lang = request.session.get('lang')
        # Проверяем наличие атрибута user перед обращением к нему
        if hasattr(request, 'user') and request.user.is_authenticated and not lang:
            lang = getattr(request.user, 'locale', 'ru')
        if lang:
            translation.activate(lang)
            request.LANGUAGE_CODE = lang
        response = self.get_response(request)
        translation.deactivate()
        return response
