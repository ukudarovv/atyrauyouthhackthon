from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

class AuthTestCase(TestCase):
    def setUp(self):
        self.client = Client()
    
    def test_register_and_login(self):
        """Тест регистрации и автологина"""
        resp = self.client.post(reverse('register'), {
            'username': 'owner1',
            'email': 'o@example.com',
            'phone': '7000000000',
            'role': 'owner',
            'locale': 'ru',
            'password1': 'pass12345test',
            'password2': 'pass12345test'
        })
        self.assertEqual(resp.status_code, 302)  # Редирект после успешной регистрации
        
        # Проверяем что пользователь создался
        user = User.objects.get(username='owner1')
        self.assertEqual(user.role, 'owner')
        self.assertEqual(user.locale, 'ru')
        
        # Проверяем доступ к защищенной странице
        resp = self.client.get(reverse('app_home'))
        self.assertEqual(resp.status_code, 200)

    def test_rbac_roles(self):
        """Тест ролевой модели"""
        # Создаем пользователей с разными ролями
        owner = User.objects.create_user(username='owner', password='pass', role='owner')
        manager = User.objects.create_user(username='manager', password='pass', role='manager')
        cashier = User.objects.create_user(username='cashier', password='pass', role='cashier')
        
        # Проверяем методы проверки ролей (строгая проверка - каждая роль только для себя)
        self.assertTrue(owner.is_owner())
        self.assertFalse(owner.is_manager())
        self.assertFalse(owner.is_cashier())
        
        self.assertFalse(manager.is_owner())
        self.assertTrue(manager.is_manager())
        self.assertFalse(manager.is_cashier())
        
        self.assertFalse(cashier.is_owner())
        self.assertFalse(cashier.is_manager())
        self.assertTrue(cashier.is_cashier())

    def test_login_required(self):
        """Тест требования авторизации"""
        # Проверяем что неавторизованный пользователь перенаправляется на логин
        resp = self.client.get(reverse('app_home'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auth/login/', resp.url)

    def test_login_logout(self):
        """Тест входа и выхода"""
        # Создаем пользователя
        user = User.objects.create_user(username='testuser', password='testpass')
        
        # Тест логина
        resp = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'testpass'
        })
        self.assertEqual(resp.status_code, 302)
        
        # Проверяем что теперь можем зайти на защищенную страницу
        resp = self.client.get(reverse('app_home'))
        self.assertEqual(resp.status_code, 200)
        
        # Тест логаута
        resp = self.client.post(reverse('logout'))
        self.assertEqual(resp.status_code, 302)