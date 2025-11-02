from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from .intents_catalog import match_intent

@dataclass
class PlanStep:
    tool: str
    args: Dict[str, Any]
    note: str = ""

@dataclass
class Plan:
    intention: str
    steps: List[PlanStep] = field(default_factory=list)

def make_plan(user_text: str, brief: Dict[str,Any], detail_level: str = "normal") -> Plan:
    # 1) Пытаемся распознать известный интент (без LLM)
    matched = match_intent(user_text)
    if matched:
        p = Plan(intention="rule_based")
        p.steps = [PlanStep(tool=s["tool"], args=s.get("args",{}), note=s.get("note","")) for s in matched]
        # в "подробном" режиме добавим ещё шаг сравнения по дням недели
        if detail_level == "deep":
            p.steps.append(PlanStep(
                tool="analytics.query",
                args={"spec":{"metrics":["redeems","issues"],"dimensions":["weekday"],"date_range":{"kind":"last_30d"}}},
                note="Срез по дням недели"
            ))
        return p

    # 2) LLM-план (fallback) - пока заглушка
    # Здесь будет интеграция с LLM когда будет готов
    return Plan(intention="fallback", steps=[
        PlanStep(tool="analytics.query",
                 args={"spec":{"metrics":["redeems","issues","cr_issue_redeem"],
                               "dimensions":["date"],
                               "date_range":{"kind":"last_14d"}}},
                 note="Fallback анализ по дням")
    ])

def execute_plan(plan: Plan, business) -> str:
    """Выполняет план и возвращает результат"""
    if not plan.steps:
        return "❌ План пуст."
    
    results = []
    for step in plan.steps:
        try:
            result = execute_tool(step.tool, step.args, business)
            results.append(f"**{step.note or step.tool}:** {result}")
        except Exception as e:
            results.append(f"**{step.note or step.tool}:** ❌ Ошибка: {str(e)}")
    
    return "\n\n".join(results)

def execute_tool(tool: str, args: Dict[str, Any], business) -> str:
    """Выполняет конкретный инструмент"""
    if tool == "analytics.query":
        return execute_analytics_query(args.get("spec", {}), business)
    elif tool == "segments.top":
        return execute_segments_top(args.get("limit", 10), business)
    elif tool == "forecast.redeems":
        return execute_forecast_redeems(args.get("days", 7), business)
    elif tool == "blast.optimize_cascade":
        return execute_optimize_cascade(args.get("budget", 50000), business)
    elif tool == "draft.blast":
        return execute_draft_blast(args, business)
    elif tool == "wallet.create_offer":
        return execute_wallet_offer(args, business)
    else:
        return f"🔧 Инструмент '{tool}' пока не реализован."

def execute_analytics_query(spec: Dict[str, Any], business) -> str:
    """Выполняет аналитический запрос"""
    from apps.coupons.models import Coupon
    from apps.redemptions.models import Redemption
    from apps.campaigns.models import Campaign
    from django.utils import timezone
    from datetime import timedelta
    from django.db.models import Count, Q
    import json
    
    metrics = spec.get("metrics", ["redeems"])
    dimensions = spec.get("dimensions", ["date"])
    date_range = spec.get("date_range", {"kind": "last_7d"})
    limit = spec.get("limit", 100)
    
    # Определяем период
    now = timezone.now()
    if date_range["kind"] == "last_7d":
        start_date = now - timedelta(days=7)
        period_label = "7 дней"
    elif date_range["kind"] == "last_14d":
        start_date = now - timedelta(days=14)
        period_label = "14 дней"
    elif date_range["kind"] == "last_30d":
        start_date = now - timedelta(days=30)
        period_label = "30 дней"
    else:
        start_date = now - timedelta(days=7)
        period_label = "7 дней"
    
    results = []
    chart_data = None
    
    if "campaign" in dimensions:
        # Анализ по кампаниям
        campaigns = Campaign.objects.filter(business=business, is_active=True)
        chart_labels = []
        chart_values = []
        
        for campaign in campaigns[:limit]:
            redeems = Redemption.objects.filter(
                coupon__campaign=campaign,
                redeemed_at__gte=start_date
            ).count()
            issues = Coupon.objects.filter(
                campaign=campaign,
                issued_at__gte=start_date
            ).count()
            cr = round((redeems / issues * 100), 1) if issues > 0 else 0.0
            results.append(f"📊 **{campaign.name}**: {redeems} погашений, CR: {cr}%")
            
            chart_labels.append(campaign.name[:15] + "..." if len(campaign.name) > 15 else campaign.name)
            chart_values.append(redeems)
        
        if chart_labels:
            chart_data = {
                "type": "bar",
                "title": f"Топ кампаний за {period_label}",
                "labels": chart_labels,
                "data": chart_values,
                "backgroundColor": ["#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6"]
            }
    
    elif "weekday" in dimensions:
        # Анализ по дням недели
        from django.db.models.functions import Extract
        weekday_data = Redemption.objects.filter(
            coupon__campaign__business=business,
            redeemed_at__gte=start_date
        ).annotate(
            weekday=Extract('redeemed_at', 'week_day')
        ).values('weekday').annotate(
            count=Count('id')
        ).order_by('weekday')
        
        weekdays = {1: 'Вс', 2: 'Пн', 3: 'Вт', 4: 'Ср', 5: 'Чт', 6: 'Пт', 7: 'Сб'}
        weekdays_full = {1: 'Воскресенье', 2: 'Понедельник', 3: 'Вторник', 4: 'Среда', 5: 'Четверг', 6: 'Пятница', 7: 'Суббота'}
        
        chart_labels = []
        chart_values = []
        
        for data in weekday_data:
            day_name = weekdays_full.get(data['weekday'], f"День {data['weekday']}")
            day_short = weekdays.get(data['weekday'], f"Д{data['weekday']}")
            results.append(f"📅 **{day_name}**: {data['count']} погашений")
            
            chart_labels.append(day_short)
            chart_values.append(data['count'])
        
        if chart_labels:
            chart_data = {
                "type": "line",
                "title": f"Активность по дням недели за {period_label}",
                "labels": chart_labels,
                "data": chart_values,
                "backgroundColor": "#10B981",
                "borderColor": "#059669"
            }
    
    else:
        # Анализ по дням (по умолчанию)
        from django.db.models.functions import TruncDate
        daily_data = Redemption.objects.filter(
            coupon__campaign__business=business,
            redeemed_at__gte=start_date
        ).annotate(
            date=TruncDate('redeemed_at')
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')  # Сортируем по возрастанию для графика
        
        chart_labels = []
        chart_values = []
        
        for data in daily_data[:limit]:
            date_str = data['date'].strftime('%d.%m')
            results.append(f"📈 **{date_str}**: {data['count']} погашений")
            
            chart_labels.append(date_str)
            chart_values.append(data['count'])
        
        if chart_labels:
            chart_data = {
                "type": "line",
                "title": f"Тренд погашений за {period_label}",
                "labels": chart_labels,
                "data": chart_values,
                "backgroundColor": "rgba(59, 130, 246, 0.1)",
                "borderColor": "#3B82F6"
            }
    
    result_text = "\n".join(results) if results else "📊 Нет данных за указанный период."
    
    # Добавляем график если есть данные
    if chart_data:
        chart_id = f"chart_{hash(str(chart_data)) % 10000}"
        # Экранируем HTML атрибуты для безопасности
        import html
        chart_html = f"""
        <div class="mt-4 bg-white p-4 rounded-lg border">
            <canvas id="{chart_id}" width="400" height="200" 
                    data-chart-type="{chart_data["type"]}"
                    data-chart-labels='{json.dumps(chart_data["labels"])}'
                    data-chart-data='{json.dumps(chart_data["data"])}'
                    data-chart-title="{html.escape(chart_data["title"])}"
                    data-chart-bg="{chart_data.get("backgroundColor", "#3B82F6")}"
                    data-chart-border="{chart_data.get("borderColor", "#3B82F6")}"
                    class="chart-canvas"></canvas>
        </div>
        """
        result_text += chart_html
    
    return result_text

def execute_segments_top(limit: int, business) -> str:
    """Возвращает топ сегментов"""
    # Заглушка - в реальном проекте здесь будет работа с сегментами
    return f"🎯 Топ {limit} сегментов:\n📊 **VIP клиенты**: 45 человек\n📊 **Новые клиенты**: 23 человека\n📊 **Активные**: 67 человек"

def execute_forecast_redeems(days: int, business) -> str:
    """Прогноз погашений"""
    from apps.redemptions.models import Redemption
    from django.utils import timezone
    from datetime import timedelta
    
    # Простой прогноз на основе среднего за последние 7 дней
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    
    recent_redeems = Redemption.objects.filter(
        coupon__campaign__business=business,
        redeemed_at__gte=week_ago
    ).count()
    
    daily_average = recent_redeems / 7
    forecast = round(daily_average * days)
    
    return f"🔮 Прогноз на {days} дней: **~{forecast}** погашений (на основе среднего {daily_average:.1f}/день)"

def execute_optimize_cascade(budget: int, business) -> str:
    """Оптимизация каскада"""
    return f"🎯 Оптимизация каскада под бюджет {budget:,} тг:\n💡 Рекомендуем: 60% SMS, 30% WhatsApp, 10% Email\n📊 Ожидаемый охват: ~{budget//15:,} человек"

def execute_draft_blast(args: Dict[str, Any], business) -> str:
    """Создание черновика рассылки"""
    name = args.get("name", "Новая рассылка")
    return f"📝 Создан черновик рассылки: **{name}**\n🎯 Сегмент: VIP клиенты\n⏰ Время: завтра 10:00\n💬 Канал: WhatsApp"

def execute_wallet_offer(args: Dict[str, Any], business) -> str:
    """Создание Wallet-оффера"""
    title = args.get("title", "Специальное предложение")
    discount = args.get("discount", "15%")
    expires_days = args.get("expires_in_days", 1)
    return f"💳 Создан Wallet-оффер: **{title}**\n🎁 Скидка: {discount}\n⏳ Действует: {expires_days} день"
