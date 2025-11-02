import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.utils import timezone
from datetime import timedelta

from apps.businesses.models import Business
from apps.campaigns.models import Campaign, TrackEvent, TrackEventType
from apps.reviews.models import Review, ReviewInvite, ReviewInviteSource
from apps.reviews.services import create_invite, external_links_from_business

User = get_user_model()

class ReviewTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='owner', password='pass', role='owner')
        self.business = Business.objects.create(
            owner=self.user, 
            name='Coffee Fox',
            contacts={
                'google_url': 'https://g.page/coffeefox',
                '2gis_url': 'https://2gis.kz/coffeefox',
                'yandex_url': 'https://yandex.kz/profile/coffeefox'
            }
        )
        self.campaign = Campaign.objects.create(
            business=self.business,
            name='Скидка 20%',
            is_active=True
        )
        
        # Устанавливаем текущий бизнес в сессии
        session = self.client.session
        session['current_business_id'] = self.business.id
        session.save()

    def test_create_invite_service(self):
        """Тест сервиса создания приглашения"""
        inv = create_invite(
            business=self.business,
            campaign=self.campaign,
            phone='7000000001',
            email='test@example.com',
            ttl_hours=24
        )
        
        self.assertIsNotNone(inv.token)
        self.assertEqual(len(inv.token), 12)  # token_urlsafe(9) = 12 символов
        self.assertEqual(inv.phone, '7000000001')
        self.assertEqual(inv.email, 'test@example.com')
        self.assertEqual(inv.source, ReviewInviteSource.MANUAL)
        self.assertTrue(inv.is_valid())

    def test_public_review_form_flow(self):
        """Тест полного цикла публичной формы отзыва"""
        # Создаем приглашение
        inv = create_invite(business=self.business, campaign=self.campaign, phone='7000000001')
        
        # Открываем форму
        resp = self.client.get(reverse('reviews:public', args=[inv.token]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Оцените визит')
        self.assertContains(resp, self.business.name)
        
        # Отправляем отзыв
        resp = self.client.post(reverse('reviews:public', args=[inv.token]), {
            'rating': '5',
            'text': 'Отличное обслуживание!',
            'publish_consent': True
        })
        
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Спасибо!')
        
        # Проверяем что отзыв создался
        review = Review.objects.get(business=self.business)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.text, 'Отличное обслуживание!')
        self.assertEqual(review.phone, '7000000001')
        self.assertTrue(review.publish_consent)
        self.assertTrue(review.is_published)
        
        # Проверяем что приглашение помечено использованным
        inv.refresh_from_db()
        self.assertIsNotNone(inv.used_at)
        
        # Проверяем аналитику
        self.assertTrue(TrackEvent.objects.filter(
            business=self.business,
            campaign=self.campaign,
            type=TrackEventType.REVIEW_SUBMIT
        ).exists())

    def test_expired_invite(self):
        """Тест истекшего приглашения"""
        inv = create_invite(
            business=self.business,
            ttl_hours=1
        )
        
        # Делаем приглашение истекшим
        inv.expires_at = timezone.now() - timedelta(hours=2)
        inv.save()
        
        resp = self.client.get(reverse('reviews:public', args=[inv.token]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Ссылка недействительна')

    def test_used_invite(self):
        """Тест уже использованного приглашения"""
        inv = create_invite(business=self.business)
        inv.used_at = timezone.now()
        inv.save()
        
        resp = self.client.get(reverse('reviews:public', args=[inv.token]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Ссылка недействительна')

    def test_external_links_service(self):
        """Тест сервиса извлечения внешних ссылок"""
        links = external_links_from_business(self.business)
        
        self.assertEqual(links['google_url'], 'https://g.page/coffeefox')
        self.assertEqual(links['gis2_url'], 'https://2gis.kz/coffeefox')
        self.assertEqual(links['yandex_url'], 'https://yandex.kz/profile/coffeefox')

    def test_review_deeplinks_display(self):
        """Тест отображения deeplinks после отзыва"""
        inv = create_invite(business=self.business)
        
        resp = self.client.post(reverse('reviews:public', args=[inv.token]), {
            'rating': '4',
            'text': 'Хорошо!',
            'publish_consent': True
        })
        
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'https://g.page/coffeefox')
        self.assertContains(resp, 'https://2gis.kz/coffeefox')
        self.assertContains(resp, 'https://yandex.kz/profile/coffeefox')
        self.assertContains(resp, 'Оставить отзыв в Google')
        self.assertContains(resp, 'Оставить отзыв в 2ГИС')

    def test_internal_reviews_list(self):
        """Тест внутреннего списка отзывов"""
        self.client.login(username='owner', password='pass')
        
        # Создаем несколько отзывов
        Review.objects.create(business=self.business, rating=5, text='Отлично!', phone='7000000001')
        Review.objects.create(business=self.business, rating=3, text='Нормально', phone='7000000002', is_published=False)
        
        resp = self.client.get(reverse('reviews:list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Отзывы')
        self.assertContains(resp, 'Отлично!')
        self.assertContains(resp, 'Нормально')
        self.assertContains(resp, '5★')
        self.assertContains(resp, '3★')

    def test_review_detail_and_toggle_publication(self):
        """Тест детальной страницы и переключения публикации"""
        self.client.login(username='owner', password='pass')
        
        review = Review.objects.create(
            business=self.business,
            rating=4,
            text='Хороший сервис',
            phone='7000000001',
            is_published=True
        )
        
        # Открываем детальную страницу
        resp = self.client.get(reverse('reviews:detail', args=[review.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Хороший сервис')
        self.assertContains(resp, '4★')
        self.assertContains(resp, 'Опубликован')
        
        # Переключаем публикацию
        resp = self.client.post(reverse('reviews:detail', args=[review.id]))
        self.assertEqual(resp.status_code, 302)  # Редирект обратно к списку
        
        review.refresh_from_db()
        self.assertFalse(review.is_published)

    def test_invite_creation_form(self):
        """Тест формы создания приглашения"""
        self.client.login(username='owner', password='pass')
        
        resp = self.client.get(reverse('reviews:invite_new'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Создать ссылку для отзыва')
        
        resp = self.client.post(reverse('reviews:invite_new'), {
            'phone': '7000000123',
            'email': 'client@example.com',
            'campaign': self.campaign.id,
            'ttl_hours': '48'
        })
        self.assertEqual(resp.status_code, 302)  # Редирект после создания
        
        invite = ReviewInvite.objects.get(phone='7000000123')
        self.assertEqual(invite.email, 'client@example.com')
        self.assertEqual(invite.campaign, self.campaign)
        self.assertIsNotNone(invite.expires_at)

    def test_qr_code_generation(self):
        """Тест генерации QR-кода"""
        inv = create_invite(business=self.business)
        
        resp = self.client.get(reverse('reviews:invite_qr', args=[inv.token]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'image/png')

    def test_csv_export(self):
        """Тест экспорта отзывов в CSV"""
        self.client.login(username='owner', password='pass')
        
        Review.objects.create(
            business=self.business,
            campaign=self.campaign,
            rating=5,
            text='Супер!',
            phone='7000000001',
            email='test@example.com'
        )
        
        resp = self.client.get(reverse('reviews:export_csv'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv; charset=utf-8')
        
        content = resp.content.decode('utf-8')
        self.assertIn('Супер!', content)
        self.assertIn('7000000001', content)
        self.assertIn(self.campaign.name, content)

    def test_review_without_text(self):
        """Тест отзыва только с оценкой без текста"""
        inv = create_invite(business=self.business)
        
        resp = self.client.post(reverse('reviews:public', args=[inv.token]), {
            'rating': '3',
            'text': '',  # Пустой текст
            'publish_consent': False
        })
        
        self.assertEqual(resp.status_code, 200)
        
        review = Review.objects.get(business=self.business)
        self.assertEqual(review.rating, 3)
        self.assertEqual(review.text, '')
        self.assertFalse(review.publish_consent)

    def test_business_without_contacts(self):
        """Тест бизнеса без настроенных контактов"""
        business_no_contacts = Business.objects.create(
            owner=self.user,
            name='Simple Cafe'
        )
        
        links = external_links_from_business(business_no_contacts)
        self.assertEqual(links['google_url'], '')
        self.assertEqual(links['gis2_url'], '')
        self.assertEqual(links['yandex_url'], '')

    def test_review_filtering(self):
        """Тест фильтрации отзывов"""
        self.client.login(username='owner', password='pass')
        
        # Создаем отзывы с разными рейтингами и статусами
        Review.objects.create(business=self.business, rating=5, is_published=True)
        Review.objects.create(business=self.business, rating=3, is_published=False)
        Review.objects.create(business=self.business, rating=5, is_published=True)
        
        # Фильтр по рейтингу
        resp = self.client.get(reverse('reviews:list') + '?rating=5')
        self.assertEqual(resp.status_code, 200)
        # Должно быть 2 отзыва с рейтингом 5
        
        # Фильтр по публикации
        resp = self.client.get(reverse('reviews:list') + '?published=1')
        self.assertEqual(resp.status_code, 200)
        # Должно быть 2 опубликованных отзыва
        
        resp = self.client.get(reverse('reviews:list') + '?published=0')
        self.assertEqual(resp.status_code, 200)
        # Должен быть 1 скрытый отзыв