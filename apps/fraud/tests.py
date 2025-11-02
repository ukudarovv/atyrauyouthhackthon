import pytest
from django.test import TestCase, RequestFactory
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta

from apps.businesses.models import Business
from apps.campaigns.models import Campaign
from apps.coupons.models import Coupon
from apps.fraud.services import score_issue, score_redeem, _get_fraud_settings, _in_night
from apps.fraud.models import RiskEvent, RiskDecision, RiskKind

User = get_user_model()

class FraudDetectionTestCase(TestCase):
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testowner', 
            password='testpass123',
            role='owner'
        )
        
        self.business = Business.objects.create(
            owner=self.user,
            name='Test Cafe'
        )
        
        self.campaign = Campaign.objects.create(
            business=self.business,
            name='Test Campaign',
            is_active=True
        )

    def test_fraud_settings_default(self):
        """Тест получения настроек по умолчанию"""
        settings = _get_fraud_settings(self.business)
        
        self.assertEqual(settings['issue_ip_per_hour'], 20)
        self.assertEqual(settings['phone_per_day'], 2)
        self.assertEqual(settings['action_thresholds']['warn'], 20)
        self.assertEqual(settings['action_thresholds']['block'], 50)

    def test_fraud_settings_custom(self):
        """Тест кастомных настроек антифрода"""
        self.business.settings = {
            'fraud': {
                'issue_ip_per_hour': 5,
                'action_thresholds': {'warn': 10, 'block': 30}
            }
        }
        self.business.save()
        
        settings = _get_fraud_settings(self.business)
        
        self.assertEqual(settings['issue_ip_per_hour'], 5)
        self.assertEqual(settings['action_thresholds']['warn'], 10)
        self.assertEqual(settings['action_thresholds']['block'], 30)

    def test_night_hours_detection(self):
        """Тест определения ночных часов"""
        now = timezone.now().replace(hour=2, minute=30)  # 02:30
        
        # Ночные часы [0, 6] - с 00:00 до 06:00
        self.assertTrue(_in_night(now, [0, 6]))
        
        # Дневные часы [9, 18] - с 09:00 до 18:00
        # Но это не ночные часы, поэтому должно быть False для обычного времени
        now = now.replace(hour=14)  # 14:00
        self.assertFalse(_in_night(now, [0, 6]))  # Проверяем против ночных часов
        
        # Ночь через полночь [22, 6]
        now = now.replace(hour=23)  # 23:00
        self.assertTrue(_in_night(now, [22, 6]))

    def test_score_issue_allow(self):
        """Тест скоринга выдачи - разрешено"""
        request = self.factory.post('/test/', {'phone': '7000000000'})
        request.META['REMOTE_ADDR'] = '192.168.1.1'
        request.META['HTTP_USER_AGENT'] = 'TestAgent'
        
        score, reasons, decision = score_issue(
            request, 
            campaign=self.campaign, 
            phone='7000000000'
        )
        
        # Первая выдача должна быть разрешена
        self.assertEqual(decision, RiskDecision.ALLOW)
        self.assertLessEqual(score, 19)  # Меньше порога warn
        
        # Проверяем, что событие записано
        event = RiskEvent.objects.filter(
            business=self.business,
            kind=RiskKind.ISSUE,
            phone='7000000000'
        ).first()
        
        self.assertIsNotNone(event)
        self.assertEqual(event.decision, RiskDecision.ALLOW)

    def test_score_issue_warn_phone_limit(self):
        """Тест скоринга - предупреждение при превышении лимита на телефон"""
        request = self.factory.post('/test/', {'phone': '7000000001'})
        request.META['REMOTE_ADDR'] = '192.168.1.2'
        
        # Создаем уже существующие купоны на этот номер
        for i in range(3):  # Превышаем лимит phone_per_day=2
            Coupon.objects.create(
                campaign=self.campaign,
                phone='7000000001',
                code=f'TEST{i:04d}',
                issued_at=timezone.now() - timedelta(hours=1)
            )
        
        score, reasons, decision = score_issue(
            request, 
            campaign=self.campaign, 
            phone='7000000001'
        )
        
        # Должно быть предупреждение или блокировка
        self.assertIn(decision, [RiskDecision.WARN, RiskDecision.BLOCK])
        self.assertGreater(score, 20)  # Больше порога warn
        
        # Проверяем причины
        phone_reasons = [r for r in reasons if 'phone_many_24h' in r]
        self.assertTrue(len(phone_reasons) > 0)

    def test_score_issue_block_deny_ip(self):
        """Тест блокировки по IP из черного списка"""
        # Добавляем IP в черный список
        self.business.settings = {
            'fraud': {
                'ip_deny': ['192.168.1.100']
            }
        }
        self.business.save()
        
        request = self.factory.post('/test/', {'phone': '7000000002'})
        request.META['REMOTE_ADDR'] = '192.168.1.100'
        
        score, reasons, decision = score_issue(
            request, 
            campaign=self.campaign, 
            phone='7000000002'
        )
        
        self.assertEqual(decision, RiskDecision.BLOCK)
        self.assertGreaterEqual(score, 50)  # Больше порога block
        
        # Проверяем причины
        deny_reasons = [r for r in reasons if 'ip_deny' in r]
        self.assertTrue(len(deny_reasons) > 0)

    def test_score_issue_allow_whitelist_ip(self):
        """Тест разрешения для IP из белого списка"""
        # Добавляем IP в белый список
        self.business.settings = {
            'fraud': {
                'ip_allow': ['192.168.1.200']
            }
        }
        self.business.save()
        
        request = self.factory.post('/test/', {'phone': '7000000003'})
        request.META['REMOTE_ADDR'] = '192.168.1.200'
        
        score, reasons, decision = score_issue(
            request, 
            campaign=self.campaign, 
            phone='7000000003'
        )
        
        self.assertEqual(decision, RiskDecision.ALLOW)
        self.assertEqual(score, 0)
        self.assertEqual(reasons, ['ip_allow:0'])

    def test_score_redeem_basic(self):
        """Тест базового скоринга при погашении"""
        coupon = Coupon.objects.create(
            campaign=self.campaign,
            phone='7000000004',
            code='REDEEM01'
        )
        
        request = self.factory.post('/redeem/', {'code': 'REDEEM01'})
        request.META['REMOTE_ADDR'] = '192.168.1.3'
        
        score, reasons, decision = score_redeem(request, coupon=coupon)
        
        # Первое погашение должно быть разрешено
        self.assertEqual(decision, RiskDecision.ALLOW)
        self.assertLessEqual(score, 19)
        
        # Проверяем событие
        event = RiskEvent.objects.filter(
            business=self.business,
            kind=RiskKind.REDEEM,
            coupon=coupon
        ).first()
        
        self.assertIsNotNone(event)
        self.assertEqual(event.decision, RiskDecision.ALLOW)

    def test_score_redeem_burst_warning(self):
        """Тест предупреждения при частых погашениях с одного IP"""
        # Создаем много событий погашения с одного IP
        ip = '192.168.1.4'
        for i in range(12):  # Превышаем лимит 10
            RiskEvent.objects.create(
                business=self.business,
                kind=RiskKind.REDEEM,
                ip=ip,
                score=0,
                decision=RiskDecision.ALLOW,
                created_at=timezone.now() - timedelta(minutes=5)
            )
        
        coupon = Coupon.objects.create(
            campaign=self.campaign,
            phone='7000000005',
            code='REDEEM02'
        )
        
        request = self.factory.post('/redeem/', {'code': 'REDEEM02'})
        request.META['REMOTE_ADDR'] = ip
        
        score, reasons, decision = score_redeem(request, coupon=coupon)
        
        # Должно быть предупреждение или блокировка
        self.assertIn(decision, [RiskDecision.WARN, RiskDecision.BLOCK])
        self.assertGreater(score, 20)
        
        # Проверяем причины
        burst_reasons = [r for r in reasons if 'redeem_burst_ip_10m' in r]
        self.assertTrue(len(burst_reasons) > 0)

    def test_night_hours_penalty(self):
        """Тест штрафа за ночные часы"""
        # Устанавливаем ночные часы
        self.business.settings = {
            'fraud': {
                'night_hours': [0, 6]  # с 00:00 до 06:00
            }
        }
        self.business.save()
        
        # Создаем запрос в ночное время
        request = self.factory.post('/test/', {'phone': '7000000006'})
        request.META['REMOTE_ADDR'] = '192.168.1.5'
        
        # Мокаем время на 2:00 ночи
        with self.settings(USE_TZ=False):
            from unittest.mock import patch
            night_time = timezone.now().replace(hour=2, minute=0, second=0, microsecond=0)
            
            with patch('apps.fraud.services.timezone.now', return_value=night_time):
                score, reasons, decision = score_issue(
                    request, 
                    campaign=self.campaign, 
                    phone='7000000006'
                )
        
        # Должен быть штраф за ночное время
        night_reasons = [r for r in reasons if 'night:+10' in r]
        self.assertTrue(len(night_reasons) > 0)
        self.assertGreaterEqual(score, 10)

    def test_utm_deny_detection(self):
        """Тест блокировки по запрещенным UTM меткам"""
        self.business.settings = {
            'fraud': {
                'utm_deny': ['spam', 'bot']
            }
        }
        self.business.save()
        
        request = self.factory.post('/test/', {
            'phone': '7000000007',
            'utm_source': 'spam-network'
        })
        request.META['REMOTE_ADDR'] = '192.168.1.6'
        
        score, reasons, decision = score_issue(
            request, 
            campaign=self.campaign, 
            phone='7000000007'
        )
        
        # Должен быть штраф за запрещенную UTM метку
        utm_reasons = [r for r in reasons if 'utm_deny' in r]
        self.assertTrue(len(utm_reasons) > 0)
        self.assertGreaterEqual(score, 50)

    def test_risk_event_creation(self):
        """Тест создания событий риска"""
        request = self.factory.post('/test/', {'phone': '7000000008'})
        request.META['REMOTE_ADDR'] = '192.168.1.7'
        request.META['HTTP_USER_AGENT'] = 'TestAgent/1.0'
        
        initial_count = RiskEvent.objects.count()
        
        score_issue(request, campaign=self.campaign, phone='7000000008')
        
        # Должно быть создано новое событие
        self.assertEqual(RiskEvent.objects.count(), initial_count + 1)
        
        event = RiskEvent.objects.latest('created_at')
        self.assertEqual(event.business, self.business)
        self.assertEqual(event.kind, RiskKind.ISSUE)
        self.assertEqual(event.phone, '7000000008')
        self.assertEqual(event.ip, '192.168.1.7')
        self.assertEqual(event.ua, 'TestAgent/1.0')
        self.assertFalse(event.resolved)
