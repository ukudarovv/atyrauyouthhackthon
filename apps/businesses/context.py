from .models import Business

def current_business(request):
    biz = None
    # Проверяем наличие session (может отсутствовать в тестах/API)
    if hasattr(request, 'session') and hasattr(request, 'user'):
        biz_id = request.session.get('current_business_id')
        if request.user.is_authenticated and biz_id:
            biz = Business.objects.filter(id=biz_id, owner=request.user).first()
    return {'current_business': biz}
