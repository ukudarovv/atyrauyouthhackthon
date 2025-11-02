def extract_utm(request):
    """Извлекает UTM параметры из запроса"""
    keys = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content']
    return {k: request.GET.get(k) for k in keys if request.GET.get(k)}

def get_client_ip(request):
    """Получает IP адрес клиента с учетом прокси"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
