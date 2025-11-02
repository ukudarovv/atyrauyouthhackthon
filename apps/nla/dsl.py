"""
DSL для спецификаций запросов к аналитике
"""

# Разрешенные метрики
ALLOWED_METRICS = {
    "views": {"model": "TrackEvent", "type": "LANDING_VIEW"},
    "clicks": {"model": "TrackEvent", "type": "LANDING_CLICK"},
    "issues": {"model": "TrackEvent", "type": "COUPON_ISSUE"},
    "redeems": {"model": "TrackEvent", "type": "COUPON_REDEEM"},
    # производные (считаем в питоне)
    "cr_click_issue": {"derived": True, "depends": ["clicks", "issues"]},
    "cr_issue_redeem": {"derived": True, "depends": ["issues", "redeems"]},
}

# Разрешенные измерения
ALLOWED_DIMENSIONS = {
    "date": {"field": "created_at__date"},   # TruncDate
    "hour": {"field": "created_at__hour"},   # TruncHour
    "campaign": {"field": "campaign__name"},
    "variant": {"field": "variant__key"},
    "source": {"field": "utm__utm_source"},  # если храните utm в TrackEvent.utm JSON
}

# Поддерживаемые диапазоны
SUPPORTED_RANGES = {
    "today", "yesterday", "last_7d", "last_14d", "last_30d", 
    "this_month", "last_month", "custom"
}

def normalize_range(params, tz=None):
    """
    Нормализует диапазон дат
    """
    from django.utils import timezone
    from datetime import date, timedelta
    
    today = timezone.localdate()
    kind = (params or {}).get("kind") or "last_14d"
    
    if kind == "custom":
        start_str = params.get("start")
        end_str = params.get("end")
        if start_str and end_str:
            from datetime import datetime
            start = datetime.strptime(start_str, "%Y-%m-%d").date()
            end = datetime.strptime(end_str, "%Y-%m-%d").date()
            return start, end
        return today - timedelta(days=13), today
    
    if kind == "today":
        return today, today
    
    if kind == "yesterday":
        d = today - timedelta(days=1)
        return d, d
    
    if kind == "last_7d":
        return today - timedelta(days=6), today
    
    if kind == "last_14d":
        return today - timedelta(days=13), today
    
    if kind == "last_30d":
        return today - timedelta(days=29), today
    
    if kind == "this_month":
        start = today.replace(day=1)
        return start, today
    
    if kind == "last_month":
        # Первый день предыдущего месяца
        start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        # Последний день предыдущего месяца
        end = start.replace(day=28) + timedelta(days=4)
        end = end.replace(day=1) - timedelta(days=1)
        return start, end
    
    # По умолчанию - последние 14 дней
    return today - timedelta(days=13), today

def validate_spec(spec):
    """
    Валидирует спецификацию запроса
    """
    if not isinstance(spec, dict):
        return False
    
    # Проверяем метрики
    metrics = spec.get("metrics", [])
    if not isinstance(metrics, list):
        return False
    
    for metric in metrics:
        if metric not in ALLOWED_METRICS:
            return False
    
    # Проверяем измерения
    dimensions = spec.get("dimensions", [])
    if not isinstance(dimensions, list):
        return False
    
    for dim in dimensions:
        if dim not in ALLOWED_DIMENSIONS:
            return False
    
    # Проверяем диапазон дат
    date_range = spec.get("date_range", {})
    if not isinstance(date_range, dict):
        return False
    
    kind = date_range.get("kind")
    if kind and kind not in SUPPORTED_RANGES:
        return False
    
    return True
