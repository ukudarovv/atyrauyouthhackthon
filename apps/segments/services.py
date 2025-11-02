"""
Сервисы для построения сегментов и рекомендаций
"""
import logging
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from apps.customers.models import Customer

logger = logging.getLogger(__name__)

# Разрешенные поля для фильтрации
ALLOWED_FIELDS = {
    "recency_days": "recency_days",
    "issues_count": "issues_count", 
    "redeems_count": "redeems_count",
    "r_score": "r_score",
    "f_score": "f_score",
    "m_score": "m_score",
    "redeem_amount_total": "redeem_amount_total",
    # вычисляемые поля
    "first_seen_days_ago": "first_seen",
    "last_issue_days_ago": "last_issue_at",
    "last_redeem_days_ago": "last_redeem_at",
}

# Разрешенные операторы
ALLOWED_OPERATORS = ['<=', '>=', '=', '>', '<', 'between']


def _days_ago_filter(field_name: str, days: int, operator: str) -> Q:
    """
    Создает фильтр для полей типа "дней назад"
    """
    target_date = timezone.now() - timedelta(days=int(days))
    
    operator_mapping = {
        "<=": f"{field_name}__gte",  # меньше дней назад = дата позже
        ">=": f"{field_name}__lte",  # больше дней назад = дата раньше
        ">": f"{field_name}__lt",
        "<": f"{field_name}__gt",
        "=": f"{field_name}__date",
    }
    
    if operator not in operator_mapping:
        return Q()
    
    lookup = operator_mapping[operator]
    if operator == "=":
        return Q(**{lookup: target_date.date()})
    else:
        return Q(**{lookup: target_date})


def q_from_condition(condition: dict) -> Q:
    """
    Преобразует условие в Django Q объект
    """
    field = condition.get("field")
    operator = condition.get("op")
    value = condition.get("value")
    
    if not field or not operator or value is None:
        return Q()
    
    if field not in ALLOWED_FIELDS:
        logger.warning(f"Unknown field in condition: {field}")
        return Q()
    
    if operator not in ALLOWED_OPERATORS:
        logger.warning(f"Unknown operator in condition: {operator}")
        return Q()
    
    real_field = ALLOWED_FIELDS[field]
    
    # Обработка полей "дней назад"
    if field.endswith("_days_ago"):
        return _days_ago_filter(real_field, value, operator)
    
    # Обычные числовые поля
    if operator == "<=":
        return Q(**{f"{real_field}__lte": value})
    elif operator == ">=":
        return Q(**{f"{real_field}__gte": value})
    elif operator == "<":
        return Q(**{f"{real_field}__lt": value})
    elif operator == ">":
        return Q(**{f"{real_field}__gt": value})
    elif operator == "=":
        return Q(**{f"{real_field}": value})
    elif operator == "between":
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return Q(**{
                f"{real_field}__gte": value[0],
                f"{real_field}__lte": value[1]
            })
    
    return Q()


def build_queryset(business, definition: dict):
    """
    Строит QuerySet на основе определения сегмента
    """
    if not definition:
        return Customer.objects.filter(business=business)
    
    logic = definition.get("logic", "all")
    conditions = definition.get("conds", [])
    
    base_q = Q(business=business)
    
    if not conditions:
        return Customer.objects.filter(base_q)
    
    # Строим условия
    condition_queries = []
    for condition in conditions:
        q = q_from_condition(condition)
        if q:
            condition_queries.append(q)
    
    if not condition_queries:
        return Customer.objects.filter(base_q)
    
    # Объединяем условия
    from functools import reduce
    if logic == "any":
        # OR логика
        combined_q = reduce(lambda a, b: a | b, condition_queries)
    else:
        # AND логика (по умолчанию)
        combined_q = reduce(lambda a, b: a & b, condition_queries)
    
    return Customer.objects.filter(base_q & combined_q)


def mask_phone(phone: str) -> str:
    """
    Маскирует номер телефона для превью
    """
    if not phone:
        return ""
    
    if len(phone) <= 5:
        return phone
    
    return phone[:3] + "****" + phone[-2:]


def validate_segment_definition(definition: dict) -> tuple[bool, str]:
    """
    Валидирует определение сегмента
    """
    if not isinstance(definition, dict):
        return False, "Определение должно быть JSON объектом"
    
    logic = definition.get("logic", "all")
    if logic not in ["all", "any"]:
        return False, "Логика должна быть 'all' или 'any'"
    
    conditions = definition.get("conds", [])
    if not isinstance(conditions, list):
        return False, "Условия должны быть массивом"
    
    for i, condition in enumerate(conditions):
        if not isinstance(condition, dict):
            return False, f"Условие {i+1} должно быть объектом"
        
        field = condition.get("field")
        operator = condition.get("op")
        value = condition.get("value")
        
        if not field:
            return False, f"Условие {i+1}: отсутствует поле 'field'"
        
        if field not in ALLOWED_FIELDS:
            return False, f"Условие {i+1}: неизвестное поле '{field}'"
        
        if not operator:
            return False, f"Условие {i+1}: отсутствует оператор 'op'"
        
        if operator not in ALLOWED_OPERATORS:
            return False, f"Условие {i+1}: неизвестный оператор '{operator}'"
        
        if value is None:
            return False, f"Условие {i+1}: отсутствует значение 'value'"
        
        if operator == "between":
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                return False, f"Условие {i+1}: для оператора 'between' значение должно быть массивом из 2 элементов"
    
    return True, "OK"


def recommend_promo(segment) -> dict:
    """
    Возвращает рекомендации для промо-кампании на основе сегмента
    """
    name = segment.name.lower()
    slug = segment.slug.lower()
    
    # Анализируем название и slug сегмента
    if any(keyword in name or keyword in slug for keyword in ['vip', 'premium', 'золот', 'платин']):
        return {
            "discount": "15-25%",
            "duration_days": 14,
            "cta": "Премиум-предложение для VIP",
            "notes": "Подчеркните эксклюзивность, ограничьте по времени. Добавьте персональное обращение.",
            "recommended_channels": ["email", "push"],
            "timing": "Лучшее время: вечер рабочих дней"
        }
    
    if any(keyword in name or keyword in slug for keyword in ['churn', 'risk', 'отток', 'уход']):
        return {
            "discount": "10-15%",
            "duration_days": 7,
            "cta": "Вернитесь с выгодой!",
            "notes": "Короткий срок действия, реферальный бонус, напоминания через 2-3 дня.",
            "recommended_channels": ["sms", "email"],
            "timing": "Отправить в выходные для лучшего отклика"
        }
    
    if any(keyword in name or keyword in slug for keyword in ['new', 'нов', 'welcome', 'добро']):
        return {
            "discount": "10%",
            "duration_days": 14,
            "cta": "Добро пожаловать! Ваша скидка",
            "notes": "Первое погашение с небольшим подарком. Покажите ассортимент.",
            "recommended_channels": ["email", "sms"],
            "timing": "Сразу после регистрации + напоминание через 3 дня"
        }
    
    if any(keyword in name or keyword in slug for keyword in ['active', 'актив', 'частый', 'лояльн']):
        return {
            "discount": "12-18%",
            "duration_days": 10,
            "cta": "Спасибо за активность!",
            "notes": "Бонус за лояльность, предложите попробовать новые позиции.",
            "recommended_channels": ["push", "email"],
            "timing": "Лучше в середине недели"
        }
    
    if any(keyword in name or keyword in slug for keyword in ['dormant', 'спящ', 'неактив', 'давно']):
        return {
            "discount": "8-12%",
            "duration_days": 21,
            "cta": "Мы скучали! Возвращайтесь",
            "notes": "Длительный срок действия, мягкий подход, покажите что изменилось.",
            "recommended_channels": ["email"],
            "timing": "Начало месяца, избегать праздников"
        }
    
    # По умолчанию
    return {
        "discount": "5-10%",
        "duration_days": 10,
        "cta": "Выгодное предложение",
        "notes": "A/B тестируйте заголовок и CTA. Добавьте ограничение по времени.",
        "recommended_channels": ["email", "push"],
        "timing": "Оптимальное время: 10-12 или 16-18 часов"
    }


def get_segment_insights(segment) -> dict:
    """
    Возвращает аналитические инсайты по сегменту
    """
    from apps.segments.models import SegmentMember
    
    members = SegmentMember.objects.filter(segment=segment).select_related('customer')
    
    if not members.exists():
        return {
            'size': 0,
            'avg_rfm': {'r': 0, 'f': 0, 'm': 0},
            'avg_recency': 0,
            'total_ltv': 0,
            'recommendations': recommend_promo(segment)
        }
    
    customers = [member.customer for member in members]
    
    # Средние RFM показатели
    avg_r = sum(c.r_score for c in customers) / len(customers)
    avg_f = sum(c.f_score for c in customers) / len(customers)
    avg_m = sum(c.m_score for c in customers) / len(customers)
    
    # Средняя давность активности
    avg_recency = sum(c.recency_days for c in customers) / len(customers)
    
    # Общий LTV
    total_ltv = sum(float(c.redeem_amount_total) for c in customers)
    
    return {
        'size': len(customers),
        'avg_rfm': {
            'r': round(avg_r, 1),
            'f': round(avg_f, 1), 
            'm': round(avg_m, 1)
        },
        'avg_recency': round(avg_recency, 1),
        'total_ltv': round(total_ltv, 2),
        'avg_ltv': round(total_ltv / len(customers), 2) if customers else 0,
        'recommendations': recommend_promo(segment)
    }


# Синхронные функции для работы без Celery
def create_system_segments_sync(business_id: int) -> int:
    """
    Синхронное создание системных сегментов
    """
    from .models import Segment, SegmentKind, SYSTEM_SEGMENTS
    from apps.businesses.models import Business
    
    try:
        business = Business.objects.get(id=business_id)
    except Business.DoesNotExist:
        return 0
    
    created_count = 0
    
    for slug, config in SYSTEM_SEGMENTS.items():
        segment, created = Segment.objects.get_or_create(
            business=business,
            slug=slug,
            defaults={
                'name': config['name'],
                'kind': SegmentKind.SYSTEM,
                'description': config['description'],
                'color': config['color'],
                'definition': config['definition'],
                'is_dynamic': True,
                'enabled': True
            }
        )
        
        if created:
            created_count += 1
            # Сразу перестраиваем новый сегмент
            rebuild_segment_sync(segment.id)
    
    return created_count


def rebuild_segment_sync(segment_id: int) -> bool:
    """
    Синхронное перестроение сегмента
    """
    from .models import Segment, SegmentMember
    from django.utils import timezone
    from django.db import transaction
    
    try:
        segment = Segment.objects.get(id=segment_id)
    except Segment.DoesNotExist:
        return False
    
    with transaction.atomic():
        # Удаляем старых участников
        SegmentMember.objects.filter(segment=segment).delete()
        
        # Строим новый QuerySet
        customers_qs = build_queryset(segment.business, segment.definition)
        
        # Создаем новых участников батчами
        batch_size = 1000
        customers_list = list(customers_qs.values_list('id', flat=True))
        
        segment_members = []
        for customer_id in customers_list:
            segment_members.append(
                SegmentMember(segment=segment, customer_id=customer_id)
            )
            
            if len(segment_members) >= batch_size:
                SegmentMember.objects.bulk_create(segment_members)
                segment_members = []
        
        # Создаем оставшиеся записи
        if segment_members:
            SegmentMember.objects.bulk_create(segment_members)
        
        # Обновляем метаданные сегмента
        total_count = len(customers_list)
        
        # Превью участников (первые 10 с маскированными телефонами)
        preview_customers = customers_qs.values_list('phone_e164', flat=True)[:10]
        preview = [mask_phone(phone) for phone in preview_customers]
        
        segment.size_cached = total_count
        segment.preview = preview
        segment.last_built_at = timezone.now()
        segment.save(update_fields=['size_cached', 'preview', 'last_built_at'])
    
    return True
