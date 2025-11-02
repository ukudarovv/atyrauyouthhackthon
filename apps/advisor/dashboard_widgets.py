from typing import Dict, Any, List
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Count, Sum, Avg, Q, F
from django.db.models.functions import TruncDate, TruncHour

class DashboardWidgets:
    """Система интерактивных виджетов для главной страницы"""
    
    def __init__(self, business):
        self.business = business
        
    def get_live_metrics(self) -> Dict[str, Any]:
        """Получает живые метрики для виджетов"""
        from apps.customers.models import Customer
        from apps.redemptions.models import Redemption
        from apps.coupons.models import Coupon
        from apps.campaigns.models import Campaign
        
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)
        
        # Основные метрики
        new_customers_today = Customer.objects.filter(
            business=self.business,
            first_seen__date=today
        ).count()
        
        redemptions_today = Redemption.objects.filter(
            coupon__campaign__business=self.business,
            redeemed_at__date=today
        ).count()
        
        coupons_issued_today = Coupon.objects.filter(
            campaign__business=self.business,
            issued_at__date=today
        ).count()
        
        active_campaigns = Campaign.objects.filter(
            business=self.business,
            is_active=True
        ).count()
        
        # Конверсия за неделю
        week_coupons = Coupon.objects.filter(
            campaign__business=self.business,
            issued_at__gte=week_ago
        ).count()
        
        week_redemptions = Redemption.objects.filter(
            coupon__campaign__business=self.business,
            redeemed_at__gte=week_ago
        ).count()
        
        conversion_rate = (week_redemptions / week_coupons * 100) if week_coupons > 0 else 0
        
        # Сравнение с вчера для трендов
        new_customers_yesterday = Customer.objects.filter(
            business=self.business,
            first_seen__date=yesterday
        ).count()
        
        redemptions_yesterday = Redemption.objects.filter(
            coupon__campaign__business=self.business,
            redeemed_at__date=yesterday
        ).count()
        
        return {
            'new_customers': {
                'value': new_customers_today,
                'change': new_customers_today - new_customers_yesterday,
                'trend': 'up' if new_customers_today > new_customers_yesterday else 'down' if new_customers_today < new_customers_yesterday else 'same'
            },
            'redemptions': {
                'value': redemptions_today,
                'change': redemptions_today - redemptions_yesterday,
                'trend': 'up' if redemptions_today > redemptions_yesterday else 'down' if redemptions_today < redemptions_yesterday else 'same'
            },
            'conversion_rate': {
                'value': round(conversion_rate, 1),
                'change': 0,  # Можно добавить сравнение с прошлой неделей
                'trend': 'same'
            },
            'active_campaigns': {
                'value': active_campaigns,
                'change': 0,
                'trend': 'same'
            }
        }
    
    def get_hourly_activity_chart(self) -> Dict[str, Any]:
        """Почасовая активность за сегодня"""
        from apps.redemptions.models import Redemption
        
        today = timezone.now().date()
        
        hourly_data = Redemption.objects.filter(
            coupon__campaign__business=self.business,
            redeemed_at__date=today
        ).annotate(
            hour=TruncHour('redeemed_at')
        ).values('hour').annotate(
            count=Count('id')
        ).order_by('hour')
        
        # Подготавливаем данные для 24 часов
        hours = list(range(24))
        data = [0] * 24
        
        for item in hourly_data:
            hour = item['hour'].hour
            data[hour] = item['count']
        
        return {
            'type': 'line',
            'title': 'Активность сегодня по часам',
            'labels': [f"{h}:00" for h in hours],
            'data': data,
            'backgroundColor': 'rgba(59, 130, 246, 0.1)',
            'borderColor': '#3B82F6'
        }
    
    def get_weekly_trend_chart(self) -> Dict[str, Any]:
        """Тренд за последние 7 дней"""
        from apps.redemptions.models import Redemption
        
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=6)  # 7 дней включая сегодня
        
        daily_data = Redemption.objects.filter(
            coupon__campaign__business=self.business,
            redeemed_at__date__gte=start_date,
            redeemed_at__date__lte=end_date
        ).annotate(
            date=TruncDate('redeemed_at')
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        
        # Подготавливаем данные для всех 7 дней
        dates = []
        data = []
        
        for i in range(7):
            date = start_date + timedelta(days=i)
            dates.append(date.strftime('%d.%m'))
            
            # Ищем данные для этой даты
            count = 0
            for item in daily_data:
                if item['date'] == date:
                    count = item['count']
                    break
            data.append(count)
        
        return {
            'type': 'line',
            'title': 'Тренд погашений за 7 дней',
            'labels': dates,
            'data': data,
            'backgroundColor': 'rgba(16, 185, 129, 0.1)',
            'borderColor': '#10B981'
        }
    
    def get_top_campaigns_widget(self) -> Dict[str, Any]:
        """Топ кампаний за неделю"""
        from apps.campaigns.models import Campaign
        from apps.redemptions.models import Redemption
        
        week_ago = timezone.now() - timedelta(days=7)
        
        campaigns = Campaign.objects.filter(
            business=self.business,
            is_active=True
        ).annotate(
            redemption_count=Count('coupons__redemption', 
                                 filter=Q(coupons__redemption__redeemed_at__gte=week_ago))
        ).order_by('-redemption_count')[:5]
        
        labels = []
        data = []
        colors = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6']
        
        for i, campaign in enumerate(campaigns):
            name = campaign.name[:20] + '...' if len(campaign.name) > 20 else campaign.name
            labels.append(name)
            data.append(campaign.redemption_count)
        
        return {
            'type': 'doughnut',
            'title': 'Топ кампаний за неделю',
            'labels': labels,
            'data': data,
            'backgroundColor': colors[:len(labels)]
        }
    
    def get_quick_actions(self) -> List[Dict[str, Any]]:
        """Быстрые действия на основе данных"""
        from apps.campaigns.models import Campaign
        from apps.customers.models import Customer
        
        actions = []
        
        # Проверяем неактивные кампании
        inactive_campaigns = Campaign.objects.filter(
            business=self.business,
            is_active=False
        ).count()
        
        if inactive_campaigns > 0:
            actions.append({
                'title': 'Активировать кампании',
                'description': f'У вас {inactive_campaigns} неактивных кампаний',
                'icon': '🚀',
                'color': 'blue',
                'url': '/app/campaigns/',
                'priority': 7
            })
        
        # Проверяем количество клиентов
        total_customers = Customer.objects.filter(business=self.business).count()
        
        if total_customers < 10:
            actions.append({
                'title': 'Привлечь клиентов',
                'description': 'Создайте welcome-кампанию для новых клиентов',
                'icon': '👥',
                'color': 'green',
                'url': '/app/campaigns/create/',
                'priority': 9
            })
        elif total_customers > 100 and total_customers < 500:
            actions.append({
                'title': 'Сегментировать базу',
                'description': f'{total_customers} клиентов готовы к сегментации',
                'icon': '🎯',
                'color': 'purple',
                'url': '/app/segments/',
                'priority': 6
            })
        
        # Проверяем AI Советчик
        actions.append({
            'title': 'Задать вопрос AI',
            'description': 'Получите инсайты о вашем бизнесе',
            'icon': '🤖',
            'color': 'indigo',
            'url': '/advisor/chat/',
            'priority': 5
        })
        
        # Сортируем по приоритету
        actions.sort(key=lambda x: x['priority'], reverse=True)
        
        return actions[:4]  # Топ 4 действия
    
    def get_performance_score(self) -> Dict[str, Any]:
        """Общий скор производительности"""
        from apps.customers.models import Customer
        from apps.redemptions.models import Redemption
        from apps.coupons.models import Coupon
        from apps.campaigns.models import Campaign
        
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        
        # Метрики
        active_campaigns = Campaign.objects.filter(business=self.business, is_active=True).count()
        total_customers = Customer.objects.filter(business=self.business).count()
        week_new_customers = Customer.objects.filter(
            business=self.business,
            first_seen__gte=week_ago
        ).count()
        
        week_coupons = Coupon.objects.filter(
            campaign__business=self.business,
            issued_at__gte=week_ago
        ).count()
        
        week_redemptions = Redemption.objects.filter(
            coupon__campaign__business=self.business,
            redeemed_at__gte=week_ago
        ).count()
        
        # Расчет скора (0-100)
        score = 0
        
        # Активные кампании (0-25 баллов)
        if active_campaigns >= 3:
            score += 25
        elif active_campaigns >= 1:
            score += 15
        
        # Рост клиентской базы (0-25 баллов)
        if total_customers > 0:
            growth_rate = (week_new_customers / total_customers) * 100
            if growth_rate > 10:
                score += 25
            elif growth_rate > 5:
                score += 15
            elif growth_rate > 1:
                score += 10
        
        # Конверсия (0-25 баллов)
        if week_coupons > 0:
            cr = (week_redemptions / week_coupons) * 100
            if cr > 40:
                score += 25
            elif cr > 20:
                score += 15
            elif cr > 10:
                score += 10
        
        # Активность (0-25 баллов)
        if week_redemptions > 50:
            score += 25
        elif week_redemptions > 20:
            score += 15
        elif week_redemptions > 5:
            score += 10
        
        # Определяем уровень
        if score >= 80:
            level = {'text': 'Отлично', 'color': 'green', 'emoji': '🚀'}
        elif score >= 60:
            level = {'text': 'Хорошо', 'color': 'blue', 'emoji': '😊'}
        elif score >= 40:
            level = {'text': 'Средне', 'color': 'yellow', 'emoji': '😐'}
        else:
            level = {'text': 'Нужно улучшить', 'color': 'red', 'emoji': '⚠️'}
        
        return {
            'score': score,
            'level': level,
            'metrics': {
                'campaigns': active_campaigns,
                'customers': total_customers,
                'growth': week_new_customers,
                'conversion': round((week_redemptions / week_coupons * 100), 1) if week_coupons > 0 else 0
            }
        }
    
    def get_recent_activity(self) -> List[Dict[str, Any]]:
        """Последние активности"""
        from apps.redemptions.models import Redemption
        from apps.customers.models import Customer
        
        activities = []
        
        # Последние погашения
        recent_redemptions = Redemption.objects.filter(
            coupon__campaign__business=self.business
        ).select_related('coupon__campaign', 'customer').order_by('-redeemed_at')[:5]
        
        for redemption in recent_redemptions:
            activities.append({
                'type': 'redemption',
                'title': f'Погашение купона',
                'description': f'{redemption.customer.phone} погасил купон из "{redemption.coupon.campaign.name}"',
                'time': redemption.redeemed_at,
                'icon': '✅',
                'color': 'green'
            })
        
        # Новые клиенты
        recent_customers = Customer.objects.filter(
            business=self.business
        ).order_by('-first_seen')[:3]
        
        for customer in recent_customers:
            activities.append({
                'type': 'new_customer',
                'title': 'Новый клиент',
                'description': f'{customer.phone} присоединился к программе',
                'time': customer.first_seen,
                'icon': '👋',
                'color': 'blue'
            })
        
        # Сортируем по времени
        activities.sort(key=lambda x: x['time'], reverse=True)
        
        return activities[:8]  # Последние 8 активностей
