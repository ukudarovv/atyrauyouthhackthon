from typing import List, Dict, Any
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Count, Avg, Sum, Q, F
from django.db.models.functions import TruncDate, TruncHour
import random

class AIInsightsEngine:
    """Движок для генерации AI-инсайтов и рекомендаций"""
    
    def __init__(self, business):
        self.business = business
        
    def generate_insights(self) -> List[Dict[str, Any]]:
        """Генерирует список инсайтов для бизнеса"""
        insights = []
        
        # Анализ трендов
        insights.extend(self._analyze_trends())
        
        # Анализ аномалий
        insights.extend(self._detect_anomalies())
        
        # Рекомендации по оптимизации
        insights.extend(self._generate_optimization_recommendations())
        
        # Прогнозы
        insights.extend(self._generate_predictions())
        
        # Сортируем по важности
        insights.sort(key=lambda x: x.get('priority', 0), reverse=True)
        
        return insights[:10]  # Топ 10 инсайтов
    
    def _analyze_trends(self) -> List[Dict[str, Any]]:
        """Анализ трендов в данных"""
        from apps.redemptions.models import Redemption
        from apps.coupons.models import Coupon
        from apps.customers.models import Customer
        
        insights = []
        now = timezone.now()
        
        # Тренд новых клиентов
        this_week = Customer.objects.filter(
            business=self.business,
            first_seen__gte=now - timedelta(days=7)
        ).count()
        
        last_week = Customer.objects.filter(
            business=self.business,
            first_seen__gte=now - timedelta(days=14),
            first_seen__lt=now - timedelta(days=7)
        ).count()
        
        if last_week > 0 and this_week > last_week * 1.2:
            insights.append({
                'type': 'trend_positive',
                'title': '📈 Рост новых клиентов',
                'description': f'На {((this_week/last_week-1)*100):.0f}% больше новых клиентов чем на прошлой неделе',
                'priority': 8,
                'action': 'Увеличьте бюджет на привлечение, пока тренд положительный',
                'icon': '🚀'
            })
        elif last_week > 0 and this_week < last_week * 0.8:
            insights.append({
                'type': 'trend_negative',
                'title': '📉 Снижение новых клиентов',
                'description': f'На {((1-this_week/last_week)*100):.0f}% меньше новых клиентов чем на прошлой неделе',
                'priority': 9,
                'action': 'Запустите дополнительные каналы привлечения или увеличьте бонусы',
                'icon': '⚠️'
            })
        elif last_week == 0 and this_week > 0:
            insights.append({
                'type': 'first_customers',
                'title': '🎉 Первые клиенты!',
                'description': f'Поздравляем! У вас {this_week} новых клиентов на этой неделе',
                'priority': 8,
                'action': 'Продолжайте привлечение и создайте welcome-кампанию',
                'icon': '🌟'
            })
        
        # Тренд конверсии
        week_coupons = Coupon.objects.filter(
            campaign__business=self.business,
            issued_at__gte=now - timedelta(days=7)
        ).count()
        
        week_redemptions = Redemption.objects.filter(
            coupon__campaign__business=self.business,
            redeemed_at__gte=now - timedelta(days=7)
        ).count()
        
        if week_coupons > 0:
            cr_this_week = (week_redemptions / week_coupons) * 100
            
            prev_week_coupons = Coupon.objects.filter(
                campaign__business=self.business,
                issued_at__gte=now - timedelta(days=14),
                issued_at__lt=now - timedelta(days=7)
            ).count()
            
            prev_week_redemptions = Redemption.objects.filter(
                coupon__campaign__business=self.business,
                redeemed_at__gte=now - timedelta(days=14),
                redeemed_at__lt=now - timedelta(days=7)
            ).count()
            
            if prev_week_coupons > 0:
                cr_last_week = (prev_week_redemptions / prev_week_coupons) * 100
                
                if cr_this_week > cr_last_week + 5:
                    insights.append({
                        'type': 'conversion_up',
                        'title': '🎯 Улучшение конверсии',
                        'description': f'CR вырос с {cr_last_week:.1f}% до {cr_this_week:.1f}%',
                        'priority': 7,
                        'action': 'Изучите, какие кампании работают лучше всего',
                        'icon': '📊'
                    })
        
        return insights
    
    def _detect_anomalies(self) -> List[Dict[str, Any]]:
        """Обнаружение аномалий в данных"""
        from apps.redemptions.models import Redemption
        
        insights = []
        now = timezone.now()
        
        # Аномально высокая активность в определенные часы
        hourly_activity = Redemption.objects.filter(
            coupon__campaign__business=self.business,
            redeemed_at__gte=now - timedelta(days=7)
        ).annotate(
            hour=TruncHour('redeemed_at')
        ).values('hour').annotate(
            count=Count('id')
        ).order_by('-count')
        
        if hourly_activity:
            max_activity = hourly_activity[0]
            avg_activity = sum(h['count'] for h in hourly_activity) / len(hourly_activity)
            
            if avg_activity > 0 and max_activity['count'] > avg_activity * 2:
                peak_hour = max_activity['hour'].hour
                insights.append({
                    'type': 'peak_activity',
                    'title': '⏰ Пиковая активность',
                    'description': f'В {peak_hour}:00 активность в {max_activity["count"]/avg_activity:.1f}x выше среднего',
                    'priority': 6,
                    'action': f'Планируйте рассылки и акции на {peak_hour}:00-{peak_hour+1}:00',
                    'icon': '📈'
                })
        
        # Аномально низкая активность в выходные
        weekend_activity = Redemption.objects.filter(
            coupon__campaign__business=self.business,
            redeemed_at__gte=now - timedelta(days=7),
            redeemed_at__week_day__in=[1, 7]  # Суббота и воскресенье
        ).count()
        
        weekday_activity = Redemption.objects.filter(
            coupon__campaign__business=self.business,
            redeemed_at__gte=now - timedelta(days=7),
            redeemed_at__week_day__in=[2, 3, 4, 5, 6]  # Пн-Пт
        ).count()
        
        if weekday_activity > 0 and weekend_activity > 0 and weekend_activity / weekday_activity < 0.3:
            insights.append({
                'type': 'weekend_low',
                'title': '📅 Низкая активность в выходные',
                'description': f'В выходные активность в {weekday_activity/weekend_activity:.1f}x ниже будней',
                'priority': 5,
                'action': 'Создайте специальные weekend-предложения',
                'icon': '🎮'
            })
        elif weekday_activity > 0 and weekend_activity == 0:
            insights.append({
                'type': 'weekend_zero',
                'title': '📅 Нет активности в выходные',
                'description': 'В выходные полностью отсутствует активность клиентов',
                'priority': 6,
                'action': 'Запустите weekend-кампании для активации клиентов',
                'icon': '😴'
            })
        
        return insights
    
    def _generate_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Генерация рекомендаций по оптимизации"""
        from apps.campaigns.models import Campaign
        from apps.redemptions.models import Redemption
        
        insights = []
        
        # Неэффективные кампании
        campaigns = Campaign.objects.filter(
            business=self.business,
            is_active=True
        ).annotate(
            redemption_count=Count('coupons__redemption'),
            coupon_count=Count('coupons')
        )
        
        low_performing = []
        for campaign in campaigns:
            if campaign.coupon_count > 10:  # Минимум 10 купонов
                cr = (campaign.redemption_count / campaign.coupon_count) * 100
                if cr < 15:  # CR ниже 15%
                    low_performing.append((campaign, cr))
        
        if low_performing:
            worst_campaign, worst_cr = min(low_performing, key=lambda x: x[1])
            insights.append({
                'type': 'campaign_optimization',
                'title': '🎯 Неэффективная кампания',
                'description': f'"{worst_campaign.name}" имеет CR всего {worst_cr:.1f}%',
                'priority': 8,
                'action': 'Пересмотрите условия кампании или приостановите её',
                'icon': '⚡'
            })
        
        # Рекомендации по сегментации
        total_customers = self.business.customers.count()
        if total_customers > 50:
            insights.append({
                'type': 'segmentation',
                'title': '🎯 Возможность сегментации',
                'description': f'У вас {total_customers} клиентов - достаточно для сегментации',
                'priority': 6,
                'action': 'Создайте сегменты VIP, новые клиенты, неактивные',
                'icon': '📊'
            })
        
        return insights
    
    def _generate_predictions(self) -> List[Dict[str, Any]]:
        """Генерация прогнозов"""
        from apps.redemptions.models import Redemption
        
        insights = []
        now = timezone.now()
        
        # Простой прогноз на основе тренда
        last_7_days = []
        for i in range(7):
            day_start = now - timedelta(days=i+1)
            day_end = day_start + timedelta(days=1)
            
            count = Redemption.objects.filter(
                coupon__campaign__business=self.business,
                redeemed_at__gte=day_start,
                redeemed_at__lt=day_end
            ).count()
            
            last_7_days.append(count)
        
        if len(last_7_days) >= 3:
            avg_daily = sum(last_7_days) / len(last_7_days)
            recent_avg = sum(last_7_days[:3]) / 3  # Последние 3 дня
            
            if recent_avg > avg_daily * 1.2:
                predicted = int(recent_avg * 7)
                insights.append({
                    'type': 'prediction_growth',
                    'title': '🔮 Прогноз роста',
                    'description': f'При текущем тренде ожидается ~{predicted} погашений на следующей неделе',
                    'priority': 5,
                    'action': 'Подготовьте дополнительный инвентарь',
                    'icon': '📈'
                })
            elif recent_avg < avg_daily * 0.8:
                predicted = int(recent_avg * 7)
                insights.append({
                    'type': 'prediction_decline',
                    'title': '🔮 Прогноз снижения',
                    'description': f'При текущем тренде ожидается ~{predicted} погашений на следующей неделе',
                    'priority': 7,
                    'action': 'Запланируйте активационные акции',
                    'icon': '📉'
                })
        
        return insights
    
    def get_daily_digest(self) -> Dict[str, Any]:
        """Ежедневная сводка для пользователя"""
        from apps.customers.models import Customer
        from apps.redemptions.models import Redemption
        from apps.coupons.models import Coupon
        
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        
        # Метрики за сегодня
        today_customers = Customer.objects.filter(
            business=self.business,
            first_seen__date=today
        ).count()
        
        today_redemptions = Redemption.objects.filter(
            coupon__campaign__business=self.business,
            redeemed_at__date=today
        ).count()
        
        today_coupons = Coupon.objects.filter(
            campaign__business=self.business,
            issued_at__date=today
        ).count()
        
        # Сравнение с вчера
        yesterday_customers = Customer.objects.filter(
            business=self.business,
            first_seen__date=yesterday
        ).count()
        
        yesterday_redemptions = Redemption.objects.filter(
            coupon__campaign__business=self.business,
            redeemed_at__date=yesterday
        ).count()
        
        # Определяем настроение дня
        score = 0
        if today_customers > yesterday_customers:
            score += 2
        if today_redemptions > yesterday_redemptions:
            score += 2
        if today_coupons > 0:
            score += 1
            
        if score >= 4:
            mood = {"emoji": "🚀", "text": "Отличный день!", "color": "green"}
        elif score >= 2:
            mood = {"emoji": "😊", "text": "Хороший день", "color": "blue"}
        else:
            mood = {"emoji": "😐", "text": "Обычный день", "color": "gray"}
        
        return {
            'date': today.strftime('%d.%m.%Y'),
            'mood': mood,
            'metrics': {
                'new_customers': today_customers,
                'redemptions': today_redemptions,
                'coupons_issued': today_coupons,
            },
            'changes': {
                'customers': today_customers - yesterday_customers,
                'redemptions': today_redemptions - yesterday_redemptions,
            },
            'insights': self.generate_insights()[:3]  # Топ 3 инсайта
        }

def get_business_health_score(business) -> Dict[str, Any]:
    """Оценка здоровья бизнеса по различным метрикам"""
    from apps.customers.models import Customer
    from apps.redemptions.models import Redemption
    from apps.coupons.models import Coupon
    from apps.campaigns.models import Campaign
    
    now = timezone.now()
    month_ago = now - timedelta(days=30)
    
    # Метрики
    active_campaigns = Campaign.objects.filter(business=business, is_active=True).count()
    total_customers = Customer.objects.filter(business=business).count()
    monthly_new_customers = Customer.objects.filter(
        business=business,
        first_seen__gte=month_ago
    ).count()
    
    monthly_coupons = Coupon.objects.filter(
        campaign__business=business,
        issued_at__gte=month_ago
    ).count()
    
    monthly_redemptions = Redemption.objects.filter(
        coupon__campaign__business=business,
        redeemed_at__gte=month_ago
    ).count()
    
    # Расчет скоров
    scores = {}
    
    # Активность кампаний (0-25 баллов)
    if active_campaigns == 0:
        scores['campaigns'] = 0
    elif active_campaigns <= 2:
        scores['campaigns'] = 15
    elif active_campaigns <= 5:
        scores['campaigns'] = 25
    else:
        scores['campaigns'] = 20  # Слишком много может быть плохо
    
    # Рост клиентской базы (0-25 баллов)
    if total_customers == 0:
        scores['growth'] = 0
    else:
        growth_rate = (monthly_new_customers / total_customers) * 100
        if growth_rate > 20:
            scores['growth'] = 25
        elif growth_rate > 10:
            scores['growth'] = 20
        elif growth_rate > 5:
            scores['growth'] = 15
        else:
            scores['growth'] = 10
    
    # Конверсия (0-25 баллов)
    if monthly_coupons == 0:
        scores['conversion'] = 0
    else:
        cr = (monthly_redemptions / monthly_coupons) * 100
        if cr > 50:
            scores['conversion'] = 25
        elif cr > 30:
            scores['conversion'] = 20
        elif cr > 15:
            scores['conversion'] = 15
        else:
            scores['conversion'] = 10
    
    # Активность (0-25 баллов)
    if monthly_redemptions == 0:
        scores['activity'] = 0
    elif monthly_redemptions < 10:
        scores['activity'] = 10
    elif monthly_redemptions < 50:
        scores['activity'] = 15
    elif monthly_redemptions < 100:
        scores['activity'] = 20
    else:
        scores['activity'] = 25
    
    total_score = sum(scores.values())
    
    # Определяем уровень здоровья
    if total_score >= 80:
        health_level = {"text": "Отличное", "color": "green", "emoji": "🚀"}
    elif total_score >= 60:
        health_level = {"text": "Хорошее", "color": "blue", "emoji": "😊"}
    elif total_score >= 40:
        health_level = {"text": "Среднее", "color": "yellow", "emoji": "😐"}
    else:
        health_level = {"text": "Требует внимания", "color": "red", "emoji": "⚠️"}
    
    return {
        'total_score': total_score,
        'max_score': 100,
        'level': health_level,
        'scores': scores,
        'recommendations': _get_health_recommendations(scores)
    }

def _get_health_recommendations(scores: Dict[str, int]) -> List[str]:
    """Рекомендации на основе скоров здоровья"""
    recommendations = []
    
    if scores['campaigns'] < 15:
        recommendations.append("🎯 Запустите 2-3 активные кампании для привлечения клиентов")
    
    if scores['growth'] < 15:
        recommendations.append("📈 Увеличьте инвестиции в привлечение новых клиентов")
    
    if scores['conversion'] < 15:
        recommendations.append("⚡ Оптимизируйте условия кампаний для повышения конверсии")
    
    if scores['activity'] < 15:
        recommendations.append("🔄 Активируйте неактивных клиентов специальными предложениями")
    
    if not recommendations:
        recommendations.append("🎉 Отличная работа! Продолжайте в том же духе")
    
    return recommendations
