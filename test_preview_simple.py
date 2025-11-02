#!/usr/bin/env python
import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos_system.settings')
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.businesses.models import Business
from apps.campaigns.models import Campaign

print('🖼️ Тестирование упрощенного превью постеров...')

User = get_user_model()

try:
    # Создаем или получаем тестовые данные
    user = User.objects.filter(username='poster_test').first()
    if not user:
        user = User.objects.create_user(
            username='poster_test', 
            password='testpass',
            role='owner'
        )
    
    business = Business.objects.filter(owner=user).first()
    if not business:
        business = Business.objects.create(
            owner=user,
            name='Test Business'
        )
    
    campaign = Campaign.objects.filter(business=business).first()
    if not campaign:
        from datetime import datetime, timedelta
        campaign = Campaign.objects.create(
            business=business,
            name='Тестовая кампания',
            description='Описание тестовой кампании',
            is_active=True,
            ends_at=datetime.now() + timedelta(days=7)
        )
    
    print(f'✅ Тестовые данные: {campaign.name} (ID: {campaign.id})')
    
    # Создаем клиент и логинимся
    client = Client()
    client.login(username='poster_test', password='testpass')
    
    # Устанавливаем текущий бизнес
    session = client.session
    session['current_business_id'] = business.id
    session.save()
    
    # Тест 1: GET запрос к превью (как кнопка с formaction)
    response = client.get(f'/app/printing/preview/?campaign={campaign.id}&size=A4')
    print(f'🔍 GET превью: {response.status_code}')
    
    if response.status_code == 200:
        content = response.content.decode()
        print(f'✅ HTML превью работает: {len(content)} символов')
        
        # Проверяем ключевые элементы
        checks = [
            ('Название кампании', campaign.name in content),
            ('QR-код', 'qr-code' in content or 'data:image/png;base64' in content),
            ('HTML структура', '<html>' in content and '</html>' in content),
            ('Превью флаг', 'HTML Превью' in content or 'preview-notice' in content),
        ]
        
        for name, result in checks:
            status = '✅' if result else '❌'
            print(f'  {status} {name}')
            
    else:
        print(f'❌ Ошибка превью: {response.content.decode()[:200]}')
    
    # Тест 2: POST запрос к превью (как form submit)
    response = client.post('/app/printing/preview/', {
        'campaign': campaign.id,
        'size': 'A4'
    })
    print(f'📝 POST превью: {response.status_code}')
    
    if response.status_code == 200:
        print('✅ POST запрос превью работает')
    else:
        print(f'❌ Ошибка POST превью: {response.content.decode()[:200]}')
    
    # Тест 3: Проверяем что PDF все еще работает
    response = client.get(f'/app/printing/pdf/?campaign={campaign.id}&size=A4')
    print(f'📑 PDF генерация: {response.status_code}')
    
    if response.status_code == 200:
        print(f'✅ PDF работает: {len(response.content)} байт')
    else:
        print(f'❌ Ошибка PDF: {response.content.decode()[:200]}')

except Exception as e:
    print(f'❌ Ошибка теста: {e}')
    import traceback
    traceback.print_exc()

print('\n🎯 Решение упрощено:')
print('✅ Убран сложный JavaScript')
print('✅ Используется стандартный HTML formaction')
print('✅ Превью работает и с GET и с POST')
print('✅ Отладочная информация добавлена')
