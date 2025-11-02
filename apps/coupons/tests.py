from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.businesses.models import Business
from apps.campaigns.models import Campaign, TrackEvent, TrackEventType
from .models import Coupon, CouponStatus
from .services import can_issue_for_phone, issue_coupon

User = get_user_model()

class CouponTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='owner1', password='pass', role='owner')
        self.business = Business.objects.create(owner=self.user, name='Coffee Fox')
        self.campaign = Campaign.objects.create(
            business=self.business,
            name='Скидка 20%',
            is_active=True,
            issue_limit=5,
            per_phone_limit=2
        )

    def test_claim_issue_flow(self):
        """Тест выдачи купона через публичную форму"""
        # Проверяем что форма доступна
        resp = self.client.get(reverse('coupons:claim', args=[self.campaign.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Скидка 20%')
        
        # Выдаем первый купон
        resp = self.client.post(reverse('coupons:claim', args=[self.campaign.slug]), {
            'phone': '+7 (900) 123-45-67',
            'agree': True
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Поздравляем!')
        
        # Проверяем что купон создался
        coupon = Coupon.objects.get(campaign=self.campaign, phone='+7 (900) 123-45-67')
        self.assertTrue(coupon.is_active())
        self.assertEqual(len(coupon.code), 8)
        
        # Проверяем что событие записалось
        event = TrackEvent.objects.filter(
            campaign=self.campaign,
            type=TrackEventType.COUPON_ISSUE
        ).first()
        self.assertIsNotNone(event)

    def test_per_phone_limit(self):
        """Тест лимита на номер телефона"""
        phone = '+7 (900) 123-45-67'
        
        # Выдаем первый купон
        resp = self.client.post(reverse('coupons:claim', args=[self.campaign.slug]), {
            'phone': phone,
            'agree': True
        })
        self.assertEqual(resp.status_code, 200)
        
        # Выдаем второй купон (лимит = 2)
        resp = self.client.post(reverse('coupons:claim', args=[self.campaign.slug]), {
            'phone': phone,
            'agree': True
        })
        self.assertEqual(resp.status_code, 200)
        
        # Третий купон должен быть отклонен
        resp = self.client.post(reverse('coupons:claim', args=[self.campaign.slug]), {
            'phone': phone,
            'agree': True
        })
        # Проверяем что вернулась форма (не успех)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'Поздравляем!')  # не должно быть страницы успеха
        
        # Проверяем что создалось только 2 купона
        self.assertEqual(Coupon.objects.filter(campaign=self.campaign, phone=phone).count(), 2)

    def test_campaign_limit(self):
        """Тест общего лимита кампании"""
        # Выдаем купоны до лимита (5 штук)
        for i in range(5):
            phone = f'+7 (900) 123-45-{i:02d}'
            resp = self.client.post(reverse('coupons:claim', args=[self.campaign.slug]), {
                'phone': phone,
                'agree': True
            })
            self.assertEqual(resp.status_code, 200)
        
        # Проверяем что лимит исчерпан
        self.assertEqual(self.campaign.remaining(), 0)
        
        # Попытка выдать еще один купон
        resp = self.client.post(reverse('coupons:claim', args=[self.campaign.slug]), {
            'phone': '+7 (900) 999-99-99',
            'agree': True
        })
        # Проверяем что произошел редирект (302) или остались на странице с ошибкой (200)
        self.assertIn(resp.status_code, [200, 302])
        if resp.status_code == 200:
            self.assertContains(resp, 'выданы')

    def test_check_endpoint(self):
        """Тест проверки статуса купона"""
        # Создаем купон
        coupon = Coupon.objects.create(
            campaign=self.campaign,
            code='ABCDEF01',
            phone='+7 (900) 123-45-67'
        )
        
        # Проверяем статус
        resp = self.client.get(reverse('coupons:check', args=['ABCDEF01']))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'ABCDEF01')
        self.assertContains(resp, 'Действителен')
        
        # Проверяем несуществующий код
        resp = self.client.get(reverse('coupons:check', args=['NOTEXIST']))
        self.assertEqual(resp.status_code, 404)

    def test_qr_generation(self):
        """Тест генерации QR-кода"""
        resp = self.client.get(reverse('coupons:landing_qr', args=[self.campaign.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'image/png')

    def test_csv_export(self):
        """Тест экспорта купонов в CSV"""
        # Создаем несколько купонов
        for i in range(3):
            Coupon.objects.create(
                campaign=self.campaign,
                code=f'TEST{i:04d}',
                phone=f'+7 (900) 123-45-{i:02d}'
            )
        
        # Логинимся как владелец
        self.client.login(username='owner1', password='pass')
        
        # Экспортируем все купоны
        resp = self.client.get(reverse('coupons:export_csv'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv; charset=utf-8')
        self.assertContains(resp, 'TEST0000')
        
        # Экспортируем купоны конкретной кампании
        resp = self.client.get(reverse('coupons:export_csv') + f'?campaign={self.campaign.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'TEST0000')

    def test_coupon_services(self):
        """Тест сервисных функций"""
        phone = '+7 (900) 123-45-67'
        
        # Проверяем что можно выдать купон
        self.assertTrue(can_issue_for_phone(self.campaign, phone))
        
        # Выдаем купон
        coupon = issue_coupon(self.campaign, phone)
        self.assertIsNotNone(coupon)
        self.assertTrue(coupon.is_active())
        
        # Проверяем уникальность кода
        coupon2 = issue_coupon(self.campaign, '+7 (900) 999-99-99')
        self.assertNotEqual(coupon.code, coupon2.code)

    def test_coupon_expiration(self):
        """Тест истечения срока действия купона"""
        from django.utils import timezone
        from datetime import timedelta
        
        # Создаем купон с истекшим сроком
        expired_coupon = Coupon.objects.create(
            campaign=self.campaign,
            code='EXPIRED1',
            phone='+7 (900) 123-45-67',
            expires_at=timezone.now() - timedelta(days=1)
        )
        
        self.assertTrue(expired_coupon.is_expired())
        self.assertFalse(expired_coupon.is_active())
        
        # Создаем купон с действующим сроком
        active_coupon = Coupon.objects.create(
            campaign=self.campaign,
            code='ACTIVE01',
            phone='+7 (900) 123-45-68',
            expires_at=timezone.now() + timedelta(days=1)
        )
        
        self.assertFalse(active_coupon.is_expired())
        self.assertTrue(active_coupon.is_active())