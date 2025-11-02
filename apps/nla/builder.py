"""
Безопасный построитель запросов для аналитики
"""
from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncHour
from apps.campaigns.models import TrackEvent, TrackEventType, Campaign
from .dsl import ALLOWED_METRICS, ALLOWED_DIMENSIONS, normalize_range, validate_spec

def _metric_filters(metric_key):
    """
    Возвращает фильтры для метрики
    """
    info = ALLOWED_METRICS[metric_key]
    if info.get("derived"):  # производные не фильтруют
        return Q()
    
    event_type = getattr(TrackEventType, info["type"])
    return Q(type=event_type)

def _apply_date_grain(qs, grain: str):
    """
    Применяет группировку по времени
    """
    if grain == "hour":
        return qs.annotate(bucket=TruncHour('created_at'))
    # default day
    return qs.annotate(bucket=TruncDate('created_at'))

def run_spec(business, spec: dict):
    """
    Выполняет спецификацию запроса
    
    spec = {
      "metrics": ["views","issues","cr_issue_redeem"],
      "dimensions": ["date","campaign"],
      "date_range": {"kind":"last_14d"} or {"kind":"custom","start":"2025-08-01","end":"2025-08-18"},
      "filters": {"campaign_names":["Ланч"]},
      "order_by": [{"metric":"redeems","dir":"desc"}],
      "limit": 100,
      "grain": "day"|"hour"
    }
    """
    # 1) валидация
    if not validate_spec(spec):
        raise ValueError("Неверная спецификация")
    
    metrics = [m for m in spec.get("metrics", []) if m in ALLOWED_METRICS]
    dims = [d for d in spec.get("dimensions", []) if d in ALLOWED_DIMENSIONS]
    
    if not metrics:
        metrics = ["views", "issues", "redeems"]
    
    grain = "hour" if "hour" in dims else "day"

    # 2) период
    from django.utils import timezone
    start, end = normalize_range(spec.get("date_range"), timezone.get_default_timezone())
    
    # 3) базовый queryset
    qs = TrackEvent.objects.filter(
        business=business, 
        created_at__date__gte=start, 
        created_at__date__lte=end
    )

    # фильтр по кампаниям
    filters = spec.get("filters", {}) or {}
    campaign_names = filters.get("campaign_names") or []
    
    if campaign_names:
        # Безопасный поиск по именам кампаний
        campaign_ids = list(
            Campaign.objects.filter(
                business=business, 
                name__in=campaign_names
            ).values_list('id', flat=True)
        )
        if campaign_ids:
            qs = qs.filter(campaign_id__in=campaign_ids)

    # 4) группировка
    annotations = {}
    group_fields = []
    
    if "date" in dims:
        qs = qs.annotate(date=TruncDate('created_at'))
        annotations["date"] = "date"
        group_fields.append("date")
    
    if "hour" in dims:
        qs = qs.annotate(hour=TruncHour('created_at'))
        annotations["hour"] = "hour"
        group_fields.append("hour")
    
    if "campaign" in dims:
        annotations["campaign"] = "campaign__name"
        group_fields.append("campaign__name")
    
    if "variant" in dims:
        annotations["variant"] = "variant__key"
        group_fields.append("variant__key")
    
    if "source" in dims:
        annotations["source"] = "utm__utm_source"
        group_fields.append("utm__utm_source")

    if group_fields:
        qs = qs.values(*group_fields)

    # 5) метрики-счётчики
    def cnt(q):
        return Count('id', filter=q)
    
    aggregations = {}
    
    if "views" in metrics:   
        aggregations["views"] = cnt(_metric_filters("views"))
    if "clicks" in metrics:  
        aggregations["clicks"] = cnt(_metric_filters("clicks"))
    if "issues" in metrics:  
        aggregations["issues"] = cnt(_metric_filters("issues"))
    if "redeems" in metrics: 
        aggregations["redeems"] = cnt(_metric_filters("redeems"))
    
    # Если нет базовых метрик, добавляем views для корректной работы
    if not aggregations:
        aggregations["views"] = cnt(_metric_filters("views"))
        if "views" not in metrics:
            metrics.append("views")

    rows = list(qs.annotate(**aggregations))
    
    # 6) производные метрики
    for row in rows:
        if "cr_click_issue" in metrics:
            clicks = row.get("clicks", 0) or 0
            issues = row.get("issues", 0) or 0
            row["cr_click_issue"] = round((issues / clicks * 100) if clicks else 0.0, 1)
        
        if "cr_issue_redeem" in metrics:
            issues = row.get("issues", 0) or 0
            redeems = row.get("redeems", 0) or 0
            row["cr_issue_redeem"] = round((redeems / issues * 100) if issues else 0.0, 1)

    # 7) сортировка
    order = spec.get("order_by") or []
    if order and isinstance(order, list) and len(order) > 0:
        order_item = order[0]
        if isinstance(order_item, dict):
            key = order_item.get("metric", "redeems")
            reverse = (order_item.get("dir", "desc") == "desc")
            
            if key in [col for col in (list(annotations.keys()) + metrics)]:
                rows.sort(key=lambda x: x.get(key, 0) or 0, reverse=reverse)

    # 8) лимит
    limit = min(int(spec.get("limit", 200)), 500)
    rows = rows[:limit]

    # Метаданные
    meta = {
        "start": str(start), 
        "end": str(end), 
        "metrics": metrics, 
        "dimensions": dims, 
        "filters": filters
    }
    
    return rows, meta
