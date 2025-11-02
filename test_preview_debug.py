#!/usr/bin/env python
import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos_system.settings')
django.setup()

from django.test import RequestFactory
from apps.campaigns.models import Campaign
from apps.printing.services import render_html, qr_data_uri

print('🖼️ Диагностика HTML превью постера...')

try:
    # Получаем тестовую кампанию
    campaign = Campaign.objects.first()
    if not campaign:
        print('❌ Нет кампаний для тестирования')
        sys.exit(1)
    
    print(f'✅ Тестовая кампания: {campaign.name}')
    
    # Создаем fake request
    factory = RequestFactory()
    request = factory.get('/test/')
    request.build_absolute_uri = lambda path: f'http://localhost:8000{path}'
    
    # Генерируем тестовые данные
    public_url = 'http://localhost:8000/test/'
    qr_uri = qr_data_uri(public_url)
    
    print(f'✅ QR код сгенерирован: {len(qr_uri)} символов')
    
    # Подготавливаем контекст
    context = {
        'camp': campaign,
        'landing': getattr(campaign, 'landing', None),
        'qr_uri': qr_uri,
        'brand_color': '#3B82F6',
        'public_url': public_url,
        'is_preview': True,
    }
    
    print(f'✅ Контекст подготовлен')
    print(f'   Лендинг: {context["landing"]}')
    
    # Рендерим HTML
    try:
        html = render_html(request, 'printing/poster_a4.html', context)
        print(f'✅ HTML отрендерен: {len(html)} символов')
        
        # Сохраняем для проверки
        with open('test_preview.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print('📁 HTML сохранен как test_preview.html')
        
        # Проверяем ключевые элементы
        if 'brand_color' in html:
            print('✅ brand_color найден в HTML')
        else:
            print('❌ brand_color НЕ найден в HTML')
            
        if 'QR-код' in html or 'qr-code' in html:
            print('✅ QR элементы найдены в HTML')
        else:
            print('❌ QR элементы НЕ найдены в HTML')
            
        if campaign.name in html:
            print('✅ Название кампании найдено в HTML')
        else:
            print('❌ Название кампании НЕ найдено в HTML')
            
    except Exception as e:
        print(f'❌ Ошибка рендеринга HTML: {e}')
        import traceback
        traceback.print_exc()

except Exception as e:
    print(f'❌ Общая ошибка: {e}')
    import traceback
    traceback.print_exc()

print('\n🔍 Диагностика превью завершена!')
print('Откройте test_preview.html в браузере для проверки')
