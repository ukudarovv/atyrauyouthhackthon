from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.businesses.models import Business, Location

User = get_user_model()

class BusinessFlowTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='owner1', password='pass', role='owner')
        self.client.login(username='owner1', password='pass')

    def test_create_business_and_location(self):
        """Тест онбординг-флоу создания бизнеса и локации"""
        # Онбординг шаг 1 - создание бизнеса
        resp = self.client.get(reverse('businesses:onboarding'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Шаг 1')
        
        resp = self.client.post(reverse('businesses:onboarding'), {
            'name': 'Coffee Fox',
            'phone': '7000000000',
            'address': 'Main st 1',
            'timezone': 'Asia/Atyrau',
            'brand_color': '#111827'
        })
        self.assertEqual(resp.status_code, 302)
        
        # Проверяем что бизнес создался
        business = Business.objects.get(owner=self.user)
        self.assertEqual(business.name, 'Coffee Fox')
        self.assertEqual(business.phone, '7000000000')
        
        # Проверяем что бизнес стал активным в сессии
        self.assertEqual(self.client.session['current_business_id'], business.id)
        
        # Онбординг шаг 2 - создание локации
        resp = self.client.get(reverse('businesses:onboarding'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Шаг 2')
        
        resp = self.client.post(reverse('businesses:onboarding'), {
            'name': 'Центр',
            'address': 'Main st 1',
            'is_active': True
        })
        self.assertEqual(resp.status_code, 302)
        
        # Проверяем что локация создалась
        location = Location.objects.get(business=business)
        self.assertEqual(location.name, 'Центр')
        self.assertEqual(location.business, business)
        self.assertTrue(location.is_active)

    def test_business_list_and_choose(self):
        """Тест списка бизнесов и выбора активного"""
        # Создаем бизнесы
        biz1 = Business.objects.create(owner=self.user, name='Business 1')
        biz2 = Business.objects.create(owner=self.user, name='Business 2')
        
        # Тест списка
        resp = self.client.get(reverse('businesses:list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Business 1')
        self.assertContains(resp, 'Business 2')
        
        # Тест выбора бизнеса
        resp = self.client.get(reverse('businesses:choose', kwargs={'pk': biz1.id}))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.client.session['current_business_id'], biz1.id)

    def test_location_crud(self):
        """Тест CRUD операций с локациями"""
        # Создаем бизнес и выбираем его
        business = Business.objects.create(owner=self.user, name='Test Business')
        self.client.get(reverse('businesses:choose', kwargs={'pk': business.id}))
        
        # Тест создания локации
        resp = self.client.post(reverse('businesses:location_create'), {
            'name': 'Test Location',
            'address': 'Test Address',
            'is_active': True
        })
        self.assertEqual(resp.status_code, 302)
        
        location = Location.objects.get(business=business)
        self.assertEqual(location.name, 'Test Location')
        
        # Тест списка локаций
        resp = self.client.get(reverse('businesses:locations'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Test Location')
        
        # Тест редактирования локации
        resp = self.client.post(reverse('businesses:location_edit', kwargs={'pk': location.id}), {
            'name': 'Updated Location',
            'address': 'Updated Address',
            'is_active': False
        })
        self.assertEqual(resp.status_code, 302)
        
        location.refresh_from_db()
        self.assertEqual(location.name, 'Updated Location')
        self.assertFalse(location.is_active)

    def test_security_isolation(self):
        """Тест что пользователи видят только свои бизнесы"""
        # Создаем второго пользователя
        other_user = User.objects.create_user(username='owner2', password='pass', role='owner')
        other_business = Business.objects.create(owner=other_user, name='Other Business')
        
        # Проверяем что наш пользователь не видит чужой бизнес
        resp = self.client.get(reverse('businesses:list'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'Other Business')
        
        # Проверяем что нельзя выбрать чужой бизнес
        resp = self.client.get(reverse('businesses:choose', kwargs={'pk': other_business.id}))
        self.assertEqual(resp.status_code, 404)