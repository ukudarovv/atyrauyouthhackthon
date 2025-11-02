"""
Провайдеры для преобразования естественного языка в спецификации
"""
import json
import logging
from apps.ai.providers import get_llm

logger = logging.getLogger(__name__)

# Системный промпт для Claude
SYSTEM_PROMPT = """
Ты дата-аналитик маркетплатформы купонов. Преобразуй вопрос пользователя в JSON-спецификацию запроса.

ДОСТУПНЫЕ ДАННЫЕ:
- TrackEvent: события с типами LANDING_VIEW, LANDING_CLICK, COUPON_ISSUE, COUPON_REDEEM
- Поля: created_at, campaign, variant, utm (источник трафика)
- Campaign: кампании с полем name

МЕТРИКИ:
- views: просмотры лендинга
- clicks: клики на лендинге  
- issues: выданные купоны
- redeems: погашенные купоны
- cr_click_issue: конверсия клик→выдача (%)
- cr_issue_redeem: конверсия выдача→погашение (%)

ИЗМЕРЕНИЯ:
- date: группировка по дням
- hour: группировка по часам
- campaign: группировка по кампаниям
- variant: группировка по вариантам
- source: группировка по источникам трафика

ВРЕМЕННЫЕ ДИАПАЗОНЫ:
- today, yesterday, last_7d, last_14d, last_30d, this_month, last_month
- custom с полями start/end в формате YYYY-MM-DD

ВЕРНИ СТРОГО JSON с ключами:
{
  "metrics": [список метрик],
  "dimensions": [список измерений], 
  "date_range": {"kind": "диапазон"},
  "filters": {"campaign_names": [список названий кампаний]},
  "order_by": [{"metric": "метрика", "dir": "desc|asc"}],
  "limit": число
}

ПРИМЕРЫ ПРЕОБРАЗОВАНИЙ:
"Сколько погашений за прошлую неделю?" → {"metrics": ["redeems"], "date_range": {"kind": "last_7d"}}
"CR клик-выдача по кампаниям за июль" → {"metrics": ["cr_click_issue"], "dimensions": ["campaign"], "date_range": {"kind": "custom", "start": "2025-07-01", "end": "2025-07-31"}}
"Топ 5 кампаний по погашениям за 30 дней" → {"metrics": ["redeems"], "dimensions": ["campaign"], "date_range": {"kind": "last_30d"}, "order_by": [{"metric": "redeems", "dir": "desc"}], "limit": 5}
"""

def nl_to_spec(question: str, locale: str = 'ru') -> dict:
    """
    Преобразует вопрос на естественном языке в спецификацию запроса
    """
    try:
        llm = get_llm()
        
        # Формируем пользовательский запрос
        user_prompt = f"""
Вопрос пользователя: "{question}"
Язык: {locale}

Преобразуй в JSON-спецификацию. Отвечай только валидным JSON без дополнительных комментариев.
"""
        
        # Вызываем LLM
        raw_response = llm._call(SYSTEM_PROMPT, user_prompt, max_tokens=600)
        logger.info(f"NL query: {question}")
        logger.info(f"LLM raw response: {raw_response}")
        
        # Парсим JSON
        spec = llm._parse_json(raw_response)
        logger.info(f"Parsed spec: {spec}")
        
        # Валидируем и нормализуем
        spec = _normalize_spec(spec)
        
        return spec
        
    except Exception as e:
        logger.error(f"Error in nl_to_spec: {e}")
        # Fallback - минимальная спецификация
        return {
            "metrics": ["redeems", "issues"], 
            "dimensions": ["date"], 
            "date_range": {"kind": "last_14d"}, 
            "limit": 100
        }

def _normalize_spec(spec: dict) -> dict:
    """
    Нормализует и валидирует спецификацию
    """
    from .dsl import ALLOWED_METRICS, ALLOWED_DIMENSIONS, SUPPORTED_RANGES
    
    # Проверяем базовую структуру
    if not isinstance(spec, dict):
        spec = {}
    
    # Нормализуем метрики
    metrics = spec.get("metrics", [])
    if not isinstance(metrics, list):
        metrics = []
    metrics = [m for m in metrics if m in ALLOWED_METRICS]
    if not metrics:
        metrics = ["redeems", "issues"]
    spec["metrics"] = metrics
    
    # Нормализуем измерения
    dimensions = spec.get("dimensions", [])
    if not isinstance(dimensions, list):
        dimensions = []
    dimensions = [d for d in dimensions if d in ALLOWED_DIMENSIONS]
    spec["dimensions"] = dimensions
    
    # Нормализуем диапазон дат
    date_range = spec.get("date_range", {})
    if not isinstance(date_range, dict):
        date_range = {}
    
    kind = date_range.get("kind", "last_14d")
    if kind not in SUPPORTED_RANGES:
        kind = "last_14d"
    date_range["kind"] = kind
    spec["date_range"] = date_range
    
    # Нормализуем фильтры
    filters = spec.get("filters", {})
    if not isinstance(filters, dict):
        filters = {}
    spec["filters"] = filters
    
    # Нормализуем сортировку
    order_by = spec.get("order_by", [])
    if not isinstance(order_by, list):
        order_by = []
    spec["order_by"] = order_by
    
    # Нормализуем лимит
    limit = spec.get("limit", 100)
    try:
        limit = int(limit)
        limit = max(1, min(limit, 500))  # От 1 до 500
    except (ValueError, TypeError):
        limit = 100
    spec["limit"] = limit
    
    return spec
