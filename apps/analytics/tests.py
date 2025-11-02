import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.utils import timezone
from datetime import timedelta

from apps.businesses.models import Business
from apps.campaigns.models import Campaign, TrackEvent, TrackEventType
from apps.analytics.views import _cards_data, _series_data, _top_campaigns

User = get_user_model()

class AnalyticsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='owner', password='pass', role='owner')
        self.business = Business.objects.create(owner=self.user, name='Coffee Fox')
        self.campaign = Campaign.objects.create(
            business=self.business,
            name='Скидка 20%',
            is_active=True
        )
        
        # Устанавливаем текущий бизнес в сессии
        session = self.client.session
        session['current_business_id'] = self.business.id
        session.save()

    def test_dashboard_access(self):
        """Тест доступа к дашборду аналитики"""
        self.client.login(username='owner', password='pass')
        
        resp = self.client.get(reverse('analytics:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Аналитика')
        self.assertContains(resp, 'hx-get')  # Проверяем наличие HTMX

    def test_dashboard_without_business(self):
        """Тест дашборда без выбранного бизнеса"""
        # Убираем бизнес из сессии
        session = self.client.session
        del session['current_business_id']
        session.save()
        
        self.client.login(username='owner', password='pass')
        resp = self.client.get(reverse('analytics:dashboard'))
        self.assertEqual(resp.status_code, 302)  # Редирект

    def test_cards_data_calculation(self):
        """Тест расчета данных для карточек"""
        today = timezone.localdate()
        
        # Создаем тестовые события
        TrackEvent.objects.create(
            business=self.business, 
            campaign=self.campaign, 
            type=TrackEventType.LANDING_VIEW,
            created_at=timezone.now()
        )
        TrackEvent.objects.create(
            business=self.business, 
            campaign=self.campaign, 
            type=TrackEventType.LANDING_CLICK,
            created_at=timezone.now()
        )
        TrackEvent.objects.create(
            business=self.business, 
            campaign=self.campaign, 
            type=TrackEventType.COUPON_ISSUE,
            created_at=timezone.now()
        )
        
        data = _cards_data(self.business, today, today)
        
        self.assertEqual(data['views'], 1)
        self.assertEqual(data['clicks'], 1)
        self.assertEqual(data['issues'], 1)
        self.assertEqual(data['redeems'], 0)
        self.assertEqual(data['cr_click_issue'], 100.0)  # 1/1 * 100
        self.assertEqual(data['cr_issue_redeem'], 0.0)   # 0/1 * 100

    def test_series_data_generation(self):
        """Тест генерации данных временных рядов"""
        today = timezone.localdate()
        
        # Создаем события за сегодня
        TrackEvent.objects.create(
            business=self.business, 
            campaign=self.campaign, 
            type=TrackEventType.LANDING_VIEW,
            created_at=timezone.now()
        )
        
        TrackEvent.objects.create(
            business=self.business, 
            campaign=self.campaign, 
            type=TrackEventType.COUPON_ISSUE,
            created_at=timezone.now()
        )
        
        series = _series_data(self.business, today, today)
        
        self.assertEqual(len(series), 1)  # 1 день
        
        today_data = series[0]
        self.assertEqual(today_data['date'], today.isoformat())
        self.assertEqual(today_data['view'], 1)
        self.assertEqual(today_data['issue'], 1)
        self.assertEqual(today_data['redeem'], 0)

    def test_top_campaigns_ranking(self):
        """Тест ранжирования топ кампаний"""
        today = timezone.localdate()
        
        # Создаем вторую кампанию
        campaign2 = Campaign.objects.create(
            business=self.business,
            name='Скидка 30%',
            is_active=True
        )
        
        # Больше активности для первой кампании
        for _ in range(3):
            TrackEvent.objects.create(
                business=self.business, 
                campaign=self.campaign, 
                type=TrackEventType.COUPON_REDEEM,
                created_at=timezone.now()
            )
        
        # Меньше активности для второй кампании
        TrackEvent.objects.create(
            business=self.business, 
            campaign=campaign2, 
            type=TrackEventType.COUPON_REDEEM,
            created_at=timezone.now()
        )
        
        top = _top_campaigns(self.business, today, today)
        
        self.assertEqual(len(top), 2)
        # Первая кампания должна быть выше (больше погашений)
        self.assertEqual(top[0]['campaign__name'], 'Скидка 20%')
        self.assertEqual(top[0]['redeems'], 3)
        self.assertEqual(top[1]['campaign__name'], 'Скидка 30%')
        self.assertEqual(top[1]['redeems'], 1)

    def test_cards_partial_endpoint(self):
        """Тест эндпоинта карточек"""
        self.client.login(username='owner', password='pass')
        
        today = timezone.localdate().strftime('%Y-%m-%d')
        resp = self.client.get(
            reverse('analytics:cards_partial') + f'?start={today}&end={today}'
        )
        
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Просмотры')
        self.assertContains(resp, 'Клики')
        self.assertContains(resp, 'Выдано купонов')
        self.assertContains(resp, 'Погашено купонов')

    def test_series_partial_endpoint(self):
        """Тест эндпоинта графика"""
        self.client.login(username='owner', password='pass')
        
        today = timezone.localdate().strftime('%Y-%m-%d')
        resp = self.client.get(
            reverse('analytics:series_partial') + f'?start={today}&end={today}'
        )
        
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Динамика по дням')
        self.assertContains(resp, 'metricsChart')

    def test_top_campaigns_partial_endpoint(self):
        """Тест эндпоинта топ кампаний"""
        self.client.login(username='owner', password='pass')
        
        today = timezone.localdate().strftime('%Y-%m-%d')
        resp = self.client.get(
            reverse('analytics:top_campaigns_partial') + f'?start={today}&end={today}'
        )
        
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Топ кампаний')

    def test_campaign_filtering(self):
        """Тест фильтрации по кампании"""
        today = timezone.localdate()
        
        # Создаем события для разных кампаний
        campaign2 = Campaign.objects.create(
            business=self.business,
            name='Другая кампания',
            is_active=True
        )
        
        TrackEvent.objects.create(
            business=self.business, 
            campaign=self.campaign, 
            type=TrackEventType.LANDING_VIEW,
            created_at=timezone.now()
        )
        
        TrackEvent.objects.create(
            business=self.business, 
            campaign=campaign2, 
            type=TrackEventType.LANDING_VIEW,
            created_at=timezone.now()
        )
        
        # Без фильтра - должно быть 2 просмотра
        data_all = _cards_data(self.business, today, today)
        self.assertEqual(data_all['views'], 2)
        
        # С фильтром по первой кампании - должен быть 1 просмотр
        data_filtered = _cards_data(self.business, today, today, self.campaign.id)
        self.assertEqual(data_filtered['views'], 1)

    def test_conversion_calculation(self):
        """Тест расчета конверсий"""
        today = timezone.localdate()
        
        # 10 просмотров, 5 кликов, 2 выдачи, 1 погашение
        for _ in range(10):
            TrackEvent.objects.create(
                business=self.business, 
                campaign=self.campaign, 
                type=TrackEventType.LANDING_VIEW,
                created_at=timezone.now()
            )
        
        for _ in range(5):
            TrackEvent.objects.create(
                business=self.business, 
                campaign=self.campaign, 
                type=TrackEventType.LANDING_CLICK,
                created_at=timezone.now()
            )
        
        for _ in range(2):
            TrackEvent.objects.create(
                business=self.business, 
                campaign=self.campaign, 
                type=TrackEventType.COUPON_ISSUE,
                created_at=timezone.now()
            )
        
        TrackEvent.objects.create(
            business=self.business, 
            campaign=self.campaign, 
            type=TrackEventType.COUPON_REDEEM,
            created_at=timezone.now()
        )
        
        data = _cards_data(self.business, today, today)
        
        # CR клик -> выдача: 2/5 * 100 = 40%
        self.assertEqual(data['cr_click_issue'], 40.0)
        # CR выдача -> погашение: 1/2 * 100 = 50%
        self.assertEqual(data['cr_issue_redeem'], 50.0)

    def test_date_range_validation(self):
        """Тест валидации диапазона дат"""
        self.client.login(username='owner', password='pass')
        
        # Корректный диапазон
        resp = self.client.get(reverse('analytics:dashboard') + '?start=2023-01-01&end=2023-01-31')
        self.assertEqual(resp.status_code, 200)
        
        # Некорректные даты должны обрабатываться gracefully
        resp = self.client.get(reverse('analytics:dashboard') + '?start=invalid&end=invalid')
        self.assertEqual(resp.status_code, 200)

    def test_empty_data_handling(self):
        """Тест обработки пустых данных"""
        today = timezone.localdate()
        
        # Без событий
        data = _cards_data(self.business, today, today)
        self.assertEqual(data['views'], 0)
        self.assertEqual(data['clicks'], 0)
        self.assertEqual(data['issues'], 0)
        self.assertEqual(data['redeems'], 0)
        self.assertEqual(data['cr_click_issue'], 0.0)
        self.assertEqual(data['cr_issue_redeem'], 0.0)
        
        series = _series_data(self.business, today, today)
        self.assertEqual(len(series), 1)
        self.assertEqual(series[0]['view'], 0)
        self.assertEqual(series[0]['issue'], 0)
        self.assertEqual(series[0]['redeem'], 0)
        
        top = _top_campaigns(self.business, today, today)
        self.assertEqual(len(top), 0)