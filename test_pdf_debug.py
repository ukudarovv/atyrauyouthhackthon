#!/usr/bin/env python
import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos_system.settings')
django.setup()

from apps.printing.services import (
    WEASYPRINT_AVAILABLE, REPORTLAB_AVAILABLE, 
    generate_poster_pdf_reportlab, render_pdf_from_html
)
from apps.campaigns.models import Campaign
from apps.accounts.models import User

print('🖨️ Диагностика проблем с генерацией PDF...')

print(f'WeasyPrint доступен: {WEASYPRINT_AVAILABLE}')
print(f'ReportLab доступен: {REPORTLAB_AVAILABLE}')

try:
    # Получаем тестовую кампанию
    campaign = Campaign.objects.first()
    if not campaign:
        print('❌ Нет кампаний для тестирования')
        sys.exit(1)
    
    print(f'✅ Тестовая кампания: {campaign.name}')
    
    # Тест ReportLab генерации
    if REPORTLAB_AVAILABLE:
        print('\n📄 Тестируем ReportLab генерацию...')
        try:
            pdf_bytes = generate_poster_pdf_reportlab(
                campaign=campaign,
                landing=getattr(campaign, 'landing', None),
                size='A4',
                brand_color='#3B82F6',
                public_url='https://example.com/test'
            )
            
            if pdf_bytes and len(pdf_bytes) > 0:
                print(f'✅ ReportLab: PDF сгенерирован ({len(pdf_bytes)} байт)')
                
                # Сохраняем для проверки
                with open('test_reportlab.pdf', 'wb') as f:
                    f.write(pdf_bytes)
                print('📁 Файл сохранен как test_reportlab.pdf')
            else:
                print('❌ ReportLab: PDF пустой или не сгенерирован')
                
        except Exception as e:
            print(f'❌ ReportLab ошибка: {e}')
            import traceback
            traceback.print_exc()
    
    # Тест mock PDF (fallback)
    print('\n🎭 Тестируем mock PDF генерацию...')
    try:
        test_html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Test Poster</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; }
                .header { color: #3B82F6; font-size: 24px; font-weight: bold; }
                .content { margin: 20px 0; }
            </style>
        </head>
        <body>
            <div class="header">Тестовый постер</div>
            <div class="content">
                <p>Кампания: {campaign_name}</p>
                <p>Бизнес: {business_name}</p>
                <p>Это тестовый постер для диагностики PDF генерации.</p>
            </div>
        </body>
        </html>
        '''.format(
            campaign_name=campaign.name,
            business_name=campaign.business.name
        )
        
        mock_pdf_bytes = render_pdf_from_html(
            test_html, 
            base_url='http://localhost/', 
            extra_css='@page { size: A4; margin: 10mm; }'
        )
        
        if mock_pdf_bytes and len(mock_pdf_bytes) > 0:
            print(f'✅ Mock PDF: сгенерирован ({len(mock_pdf_bytes)} байт)')
            
            # Сохраняем для проверки
            with open('test_mock.pdf', 'wb') as f:
                f.write(mock_pdf_bytes)
            print('📁 Файл сохранен как test_mock.pdf')
        else:
            print('❌ Mock PDF: пустой или не сгенерирован')
            
    except Exception as e:
        print(f'❌ Mock PDF ошибка: {e}')
        import traceback
        traceback.print_exc()
    
    # Проверяем доступность библиотек
    print('\n🔧 Проверка зависимостей:')
    
    try:
        import qrcode
        print(f'✅ qrcode: {qrcode.__version__}')
    except Exception as e:
        print(f'❌ qrcode: {e}')
    
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4, A6
        from reportlab.lib.units import mm
        from reportlab.lib.colors import black, white
        print('✅ reportlab: все модули доступны')
    except Exception as e:
        print(f'❌ reportlab: {e}')
    
    try:
        from io import BytesIO
        print('✅ BytesIO: доступен')
    except Exception as e:
        print(f'❌ BytesIO: {e}')

except Exception as e:
    print(f'❌ Общая ошибка: {e}')
    import traceback
    traceback.print_exc()

print('\n🔍 Диагностика завершена!')
print('Проверьте созданные файлы test_reportlab.pdf и test_mock.pdf')
print('Если файлы созданы и открываются - проблема в интеграции с веб-интерфейсом')
print('Если файлы пустые или поврежденные - проблема в генерации PDF')
