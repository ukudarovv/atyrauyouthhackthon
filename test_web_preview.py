#!/usr/bin/env python
import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos_system.settings')
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from apps.businesses.models import Business
from apps.campaigns.models import Campaign

print('🌐 Тестирование веб-интерфейса постеров...')

User = get_user_model()

try:
    # Создаем тестового пользователя и логинимся
    user = User.objects.filter(username='testowner').first()
    if not user:
        user = User.objects.create_user(
            username='testowner', 
            password='testpass',
            role='owner'
        )
    
    # Получаем или создаем бизнес
    business = Business.objects.filter(owner=user).first()
    if not business:
        business = Business.objects.create(
            owner=user,
            name='Test Business'
        )
    
    # Получаем или создаем кампанию
    campaign = Campaign.objects.filter(business=business).first()
    if not campaign:
        from datetime import datetime, timedelta
        campaign = Campaign.objects.create(
            business=business,
            name='Test Campaign',
            description='Test description',
            is_active=True,
            ends_at=datetime.now() + timedelta(days=7)
        )
    
    print(f'✅ Тестовые данные: {user.username}, {business.name}, {campaign.name}')
    
    # Создаем клиент и логинимся
    client = Client()
    login_success = client.login(username='testowner', password='testpass')
    print(f'✅ Логин: {login_success}')
    
    # Устанавливаем текущий бизнес в сессии
    session = client.session
    session['current_business_id'] = business.id
    session.save()
    
    # Тестируем страницу формы
    response = client.get('/app/printing/')
    print(f'📄 Форма постера: {response.status_code}')
    if response.status_code != 200:
        print(f'❌ Ошибка: {response.content.decode()[:500]}')
    else:
        print('✅ Форма загружается корректно')
    
    # Тестируем превью HTML
    preview_url = f'/app/printing/preview/?campaign={campaign.id}&size=A4'
    response = client.get(preview_url)
    print(f'🖼️ HTML превью: {response.status_code}')
    
    if response.status_code == 200:
        content = response.content.decode()
        print(f'✅ HTML превью работает: {len(content)} символов')
        
        # Проверяем ключевые элементы
        checks = [
            ('QR-код', 'qr-code' in content or 'QR' in content),
            ('Название кампании', campaign.name in content),
            ('CSS стили', '<style>' in content),
            ('HTML структура', '<html>' in content and '</html>' in content),
        ]
        
        for name, result in checks:
            status = '✅' if result else '❌'
            print(f'  {status} {name}')
            
        # Сохраняем для проверки
        with open('test_web_preview.html', 'w', encoding='utf-8') as f:
            f.write(content)
        print('📁 Превью сохранено как test_web_preview.html')
        
    else:
        print(f'❌ Ошибка превью: {response.content.decode()[:500]}')
    
    # Тестируем генерацию PDF
    pdf_url = f'/app/printing/pdf/?campaign={campaign.id}&size=A4'
    response = client.get(pdf_url)
    print(f'📑 PDF генерация: {response.status_code}')
    
    if response.status_code == 200:
        content_type = response.get('Content-Type', '')
        content_length = len(response.content)
        print(f'✅ PDF сгенерирован: {content_type}, {content_length} байт')
        
        if content_length > 1000:  # Разумный размер PDF
            with open('test_web_poster.pdf', 'wb') as f:
                f.write(response.content)
            print('📁 PDF сохранен как test_web_poster.pdf')
        else:
            print('⚠️ PDF кажется слишком маленьким')
            
    else:
        print(f'❌ Ошибка PDF: {response.content.decode()[:500]}')

except Exception as e:
    print(f'❌ Ошибка теста: {e}')
    import traceback
    traceback.print_exc()

print('\n🔍 Тестирование завершено!')
print('Откройте test_web_preview.html и test_web_poster.pdf для проверки результатов')
