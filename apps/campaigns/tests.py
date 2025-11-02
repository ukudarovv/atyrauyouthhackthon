from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.businesses.models import Business
from apps.campaigns.models import Campaign, Landing, TrackEvent, TrackEventType

User = get_user_model()

class CampaignTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='owner1', password='pass', role='owner')
        self.business = Business.objects.create(owner=self.user, name='Coffee Fox')
        self.client.login(username='owner1', password='pass')
        
        # Устанавливаем текущий бизнес в сессии
        session = self.client.session
        session['current_business_id'] = self.business.id
        session.save()

    def test_create_campaign_and_landing(self):
        """Тест создания кампании и автогенерации лендинга"""
        resp = self.client.post(reverse('campaigns:create'), {
            'business': self.business.id,
            'type': 'coupon',
            'name': 'Скидка 20%',
            'description': 'Получите скидку 20% на все напитки',
            'terms': '',
            'landing_theme': 'default',
            'issue_limit': 100,
            'per_phone_limit': 1,
            'is_active': True
        })
        self.assertEqual(resp.status_code, 302)
        
        # Проверяем что кампания создалась
        campaign = Campaign.objects.get(business=self.business)
        self.assertEqual(campaign.name, 'Скидка 20%')
        self.assertEqual(campaign.type, 'coupon')
        self.assertTrue(campaign.is_active)
        
        # Проверяем автогенерацию лендинга
        self.assertTrue(hasattr(campaign, 'landing'))
        landing = campaign.landing
        self.assertEqual(landing.headline, 'Скидка 20%')
        self.assertEqual(landing.body_md, 'Получите скидку 20% на все напитки')

    def test_public_landing_view_and_tracking(self):
        """Тест публичного просмотра лендинга и отслеживания событий"""
        # Создаем кампанию с лендингом
        campaign = Campaign.objects.create(
            business=self.business,
            name='Тестовая акция',
            description='Описание акции',
            is_active=True
        )
        Landing.objects.create(
            campaign=campaign,
            headline='Супер акция!',
            body_md='Получите скидку прямо сейчас',
            cta_text='Забрать скидку'
        )
        
        # Анонимный просмотр лендинга с UTM метками
        client = Client()
        resp = client.get(
            reverse('campaigns:landing_public', args=[campaign.slug]) + 
            '?utm_source=facebook&utm_medium=social&utm_campaign=test'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Супер акция!')
        self.assertContains(resp, 'Забрать скидку')
        
        # Проверяем что событие просмотра записалось
        view_event = TrackEvent.objects.filter(
            campaign=campaign,
            type=TrackEventType.LANDING_VIEW
        ).first()
        self.assertIsNotNone(view_event)
        self.assertEqual(view_event.utm['utm_source'], 'facebook')
        self.assertEqual(view_event.utm['utm_medium'], 'social')
        
        # Клик по CTA
        resp = client.get(reverse('campaigns:landing_cta', args=[campaign.slug]))
        self.assertEqual(resp.status_code, 302)
        
        # Проверяем что событие клика записалось
        click_event = TrackEvent.objects.filter(
            campaign=campaign,
            type=TrackEventType.LANDING_CLICK
        ).first()
        self.assertIsNotNone(click_event)

    def test_landing_edit(self):
        """Тест редактирования лендинга"""
        campaign = Campaign.objects.create(
            business=self.business,
            name='Тестовая кампания',
            is_active=True
        )
        
        # Редактируем лендинг
        resp = self.client.post(reverse('campaigns:landing_edit', args=[campaign.id]), {
            'headline': 'Новый заголовок',
            'body_md': 'Новое описание',
            'cta_text': 'Новая кнопка',
            'primary_color': '#ff0000'
        })
        self.assertEqual(resp.status_code, 302)
        
        # Проверяем изменения
        landing = Landing.objects.get(campaign=campaign)
        self.assertEqual(landing.headline, 'Новый заголовок')
        self.assertEqual(landing.body_md, 'Новое описание')
        self.assertEqual(landing.cta_text, 'Новая кнопка')
        self.assertEqual(landing.primary_color, '#ff0000')

    def test_campaign_slug_generation(self):
        """Тест автогенерации уникальных слагов"""
        # Первая кампания
        campaign1 = Campaign.objects.create(
            business=self.business,
            name='Акция'
        )
        
        # Вторая кампания с тем же названием
        campaign2 = Campaign.objects.create(
            business=self.business,
            name='Акция'
        )
        
        self.assertNotEqual(campaign1.slug, campaign2.slug)
        # Проверяем что слаги содержат название бизнеса и кампании
        self.assertIn('coffee-fox', campaign1.slug.lower())
        self.assertIn('coffee-fox', campaign2.slug.lower())

    def test_campaign_is_running_now(self):
        """Тест проверки активности кампании"""
        now = timezone.now()
        
        # Активная кампания без ограничений по времени
        campaign1 = Campaign.objects.create(
            business=self.business,
            name='Всегда активная',
            is_active=True
        )
        self.assertTrue(campaign1.is_running_now())
        
        # Неактивная кампания
        campaign2 = Campaign.objects.create(
            business=self.business,
            name='Неактивная',
            is_active=False
        )
        self.assertFalse(campaign2.is_running_now())
        
        # Кампания с датами в будущем
        campaign3 = Campaign.objects.create(
            business=self.business,
            name='Будущая',
            is_active=True,
            starts_at=now + timezone.timedelta(days=1),
            ends_at=now + timezone.timedelta(days=7)
        )
        self.assertFalse(campaign3.is_running_now())

    def test_security_isolation(self):
        """Тест изоляции данных между пользователями"""
        # Создаем второго пользователя
        other_user = User.objects.create_user(username='owner2', password='pass', role='owner')
        other_business = Business.objects.create(owner=other_user, name='Other Business')
        other_campaign = Campaign.objects.create(
            business=other_business,
            name='Чужая кампания',
            is_active=True
        )
        
        # Проверяем что наш пользователь не видит чужие кампании
        resp = self.client.get(reverse('campaigns:list'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'Чужая кампания')
        
        # Проверяем что нельзя редактировать чужую кампанию
        resp = self.client.get(reverse('campaigns:edit', args=[other_campaign.id]))
        self.assertEqual(resp.status_code, 404)