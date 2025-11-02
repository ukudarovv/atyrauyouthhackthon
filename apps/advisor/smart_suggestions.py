from typing import List
from django.utils import timezone
from datetime import timedelta
from .models import AdvisorMessage

def get_smart_suggestions(session) -> List[str]:
    """Генерирует умные предложения на основе истории чата"""
    
    # Получаем последние сообщения пользователя
    recent_messages = AdvisorMessage.objects.filter(
        session=session,
        role='user',
        created_at__gte=timezone.now() - timedelta(hours=24)
    ).order_by('-created_at')[:10]
    
    # Анализируем паттерны вопросов
    suggestions = []
    asked_topics = set()
    
    for msg in recent_messages:
        text = msg.content.get('text', '').lower()
        
        # Отслеживаем темы
        if any(word in text for word in ['клиент', 'customer']):
            asked_topics.add('customers')
        if any(word in text for word in ['купон', 'coupon']):
            asked_topics.add('coupons')
        if any(word in text for word in ['кампан', 'campaign']):
            asked_topics.add('campaigns')
        if any(word in text for word in ['погашен', 'redeem']):
            asked_topics.add('redemptions')
    
    # Генерируем предложения на основе контекста
    if 'customers' in asked_topics and 'redemptions' not in asked_topics:
        suggestions.append("🔄 Retention клиентов за месяц?")
        suggestions.append("📊 Средний чек по клиентам?")
    
    if 'campaigns' in asked_topics and 'coupons' not in asked_topics:
        suggestions.append("🎟️ Сколько купонов выдала каждая кампания?")
        suggestions.append("📈 CR по кампаниям за неделю?")
    
    if 'coupons' in asked_topics and 'redemptions' not in asked_topics:
        suggestions.append("✅ Сколько купонов погашено?")
        suggestions.append("⏳ Сколько купонов истекает завтра?")
    
    # Временные предложения
    current_hour = timezone.now().hour
    if 9 <= current_hour <= 11:
        suggestions.append("☀️ Утренняя сводка: новые клиенты за ночь?")
    elif 17 <= current_hour <= 19:
        suggestions.append("🌆 Дневная сводка: активность за день?")
    
    # Сезонные предложения
    weekday = timezone.now().weekday()
    if weekday == 0:  # Понедельник
        suggestions.append("📅 Как прошли выходные? Статистика за субботу-воскресенье")
    elif weekday == 4:  # Пятница
        suggestions.append("🎉 Итоги недели: топ кампаний за 7 дней?")
    
    # Ограничиваем количество предложений
    return suggestions[:4]

def get_contextual_tips(business) -> List[str]:
    """Генерирует контекстуальные советы на основе данных бизнеса"""
    from apps.customers.models import Customer
    from apps.coupons.models import Coupon
    from apps.redemptions.models import Redemption
    from apps.campaigns.models import Campaign
    
    tips = []
    
    # Анализируем текущее состояние
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)
    
    # Новые клиенты
    today_customers = Customer.objects.filter(
        business=business, 
        first_seen__date=today
    ).count()
    
    yesterday_customers = Customer.objects.filter(
        business=business, 
        first_seen__date=yesterday
    ).count()
    
    if today_customers > yesterday_customers * 1.5:
        tips.append("🚀 У вас сегодня на 50%+ больше новых клиентов! Стоит узнать подробности")
    elif today_customers < yesterday_customers * 0.5:
        tips.append("⚠️ Сегодня мало новых клиентов. Может, стоит запустить привлекающую кампанию?")
    
    # Активные кампании
    active_campaigns = Campaign.objects.filter(business=business, is_active=True).count()
    if active_campaigns == 0:
        tips.append("💡 У вас нет активных кампаний. Создайте новую для привлечения клиентов!")
    elif active_campaigns > 5:
        tips.append("🎯 Много активных кампаний. Проанализируйте их эффективность")
    
    # CR анализ
    week_ago = today - timedelta(days=7)
    week_coupons = Coupon.objects.filter(
        campaign__business=business,
        issued_at__date__gte=week_ago
    ).count()
    
    week_redemptions = Redemption.objects.filter(
        coupon__campaign__business=business,
        redeemed_at__date__gte=week_ago
    ).count()
    
    if week_coupons > 0:
        cr = (week_redemptions / week_coupons) * 100
        if cr < 20:
            tips.append("📉 Низкий CR за неделю. Стоит оптимизировать кампании или каналы")
        elif cr > 60:
            tips.append("🎉 Отличный CR! Можно масштабировать успешные кампании")
    
    return tips[:3]
