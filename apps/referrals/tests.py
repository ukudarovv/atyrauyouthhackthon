import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.utils import timezone
from datetime import timedelta

from apps.businesses.models import Business
from apps.campaigns.models import Campaign, TrackEvent, TrackEventType
from apps.coupons.models import Coupon
from apps.referrals.models import Customer, Referral, RewardStatus, CustomerSource
from apps.referrals.services import create_referral_for_referrer

User = get_user_model()

class ReferralTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='owner', password='pass', role='owner')
        self.business = Business.objects.create(owner=self.user, name='Coffee Fox')
        self.campaign = Campaign.objects.create(
            business=self.business,
            name='Скидка 20%',
            is_active=True,
            starts_at=timezone.now() - timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=7)
        )
        
        # Устанавливаем текущий бизнес в сессии
        session = self.client.session
        session['current_business_id'] = self.business.id
        session.save()

    def test_referral_claim_and_grant_flow(self):
        """Тест полного цикла реферальной системы"""
        # 1. Создаем реферера
        referrer = Customer.objects.create(
            business=self.business, 
            phone='7000000001', 
            name='Referrer User'
        )
        ref = create_referral_for_referrer(business=self.business, referrer_customer=referrer)
        
        # 2. Переход по реферальной ссылке
        resp = self.client.get(reverse('referrals:referral_entry', args=[ref.token]))
        self.assertIn(resp.status_code, [200, 302])  # может быть редирект на лендинг
        
        # Проверяем что событие записалось
        self.assertTrue(TrackEvent.objects.filter(
            business=self.business,
            type=TrackEventType.REFERRAL_CLICK
        ).exists())
        
        # Проверяем что токен сохранился в сессии
        self.assertEqual(self.client.session.get('ref_token'), ref.token)
        
        # 3. Друг получает купон
        resp = self.client.post(reverse('coupons:claim', args=[self.campaign.slug]), {
            'phone': '7000000002',
            'agree': True
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Поздравляем!')
        
        # 4. Проверяем что реферал связался
        ref.refresh_from_db()
        self.assertIsNotNone(ref.referee)
        self.assertEqual(ref.referee.phone, '7000000002')
        self.assertEqual(ref.reward_status, RewardStatus.PENDING)
        
        # 5. Друг погашает купон (имитация)
        coupon = Coupon.objects.get(campaign=self.campaign, phone='7000000002')
        self.assertIsNotNone(coupon)
        
        # Логин для погашения
        self.client.login(username='owner', password='pass')
        resp = self.client.post(reverse('redemptions:redeem'), {
            'code': coupon.code,
            'amount': '1000.00'
        })
        self.assertIn(resp.status_code, [200, 302])  # Может быть редирект или форма с сообщением
        
        # 6. Проверяем что награда перешла в GRANTED
        ref.refresh_from_db()
        self.assertEqual(ref.reward_status, RewardStatus.GRANTED)

    def test_self_referral_prevention(self):
        """Тест защиты от самореферала"""
        # Создаем клиента
        customer = Customer.objects.create(
            business=self.business,
            phone='7000000001',
            name='Self Referrer'
        )
        ref = create_referral_for_referrer(business=self.business, referrer_customer=customer)
        
        # Переходим по ссылке
        self.client.get(reverse('referrals:referral_entry', args=[ref.token]))
        
        # Пытаемся получить купон на тот же номер
        resp = self.client.post(reverse('coupons:claim', args=[self.campaign.slug]), {
            'phone': '7000000001',  # тот же номер что у реферера
            'agree': True
        })
        
        # Купон должен выдаться, но реферал не должен связаться
        ref.refresh_from_db()
        self.assertIsNone(ref.referee)  # самореферал не засчитывается

    def test_customer_creation(self):
        """Тест создания клиентов"""
        self.client.login(username='owner', password='pass')
        
        resp = self.client.post(reverse('referrals:customer_create'), {
            'phone': '7000000123',
            'name': 'Test Customer',
            'source': CustomerSource.IMPORT,
            'consent_marketing': True
        })
        self.assertEqual(resp.status_code, 302)  # Редирект после создания
        
        customer = Customer.objects.get(phone='7000000123')
        self.assertEqual(customer.name, 'Test Customer')
        self.assertEqual(customer.source, CustomerSource.IMPORT)
        self.assertTrue(customer.consent_marketing)

    def test_referral_link_generation(self):
        """Тест генерации реферальной ссылки"""
        self.client.login(username='owner', password='pass')
        
        customer = Customer.objects.create(
            business=self.business,
            phone='7000000456',
            name='Link Generator'
        )
        
        resp = self.client.get(reverse('referrals:referral_new', args=[customer.id]))
        self.assertEqual(resp.status_code, 302)  # Редирект после создания
        
        # Проверяем что ссылка создалась
        referral = Referral.objects.get(referrer=customer)
        self.assertIsNotNone(referral.token)
        self.assertEqual(len(referral.token), 12)  # token_urlsafe(9) дает 12 символов

    def test_customers_list_view(self):
        """Тест списка клиентов"""
        self.client.login(username='owner', password='pass')
        
        # Создаем несколько клиентов
        Customer.objects.create(business=self.business, phone='7000000001', name='Customer 1')
        Customer.objects.create(business=self.business, phone='7000000002', name='Customer 2')
        
        resp = self.client.get(reverse('referrals:customers'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Customer 1')
        self.assertContains(resp, 'Customer 2')
        self.assertContains(resp, '7000000001')
        self.assertContains(resp, '7000000002')

    def test_referral_entry_without_campaign(self):
        """Тест входа по реферальной ссылке без активных кампаний"""
        # Деактивируем кампанию
        self.campaign.is_active = False
        self.campaign.save()
        
        customer = Customer.objects.create(business=self.business, phone='7000000001')
        ref = create_referral_for_referrer(business=self.business, referrer_customer=customer)
        
        resp = self.client.get(reverse('referrals:referral_entry', args=[ref.token]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Вас пригласили!')
        self.assertContains(resp, self.business.name)