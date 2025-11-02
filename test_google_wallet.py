#!/usr/bin/env python
import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos_system.settings')
django.setup()

from apps.wallet.services import create_wallet_pass_for_coupon, generate_save_link
from apps.coupons.models import Coupon
from apps.campaigns.models import Campaign
from apps.businesses.models import Business
from apps.accounts.models import User

print('📱 Демонстрация Google Wallet интеграции...')

try:
    # Проверяем настройки
    from django.conf import settings
    
    required_settings = [
        'GOOGLE_WALLET_ISSUER_ID',
        'GOOGLE_WALLET_SA_KEY_JSON_BASE64',
    ]
    
    missing_settings = []
    for setting in required_settings:
        if not getattr(settings, setting, ''):
            missing_settings.append(setting)
    
    if missing_settings:
        print('❌ Отсутствуют настройки Google Wallet:')
        for setting in missing_settings:
            print(f'   • {setting}')
        print('\nДля работы с Google Wallet добавьте в .env:')
        print('GOOGLE_WALLET_ISSUER_ID=3388000000022972119')
        print('GOOGLE_WALLET_SA_KEY_JSON_BASE64=...')
        print('GOOGLE_WALLET_CLASS_ID=3388000000022972119.coffee_offer_v1')
        sys.exit(1)
    
    print('✅ Настройки Google Wallet найдены')
    print(f'   Issuer ID: {settings.GOOGLE_WALLET_ISSUER_ID}')
    
    # Получаем тестовые данные
    coupon = Coupon.objects.filter(campaign__business__isnull=False).first()
    if not coupon:
        print('❌ Нет купонов для демо. Создайте кампанию и купон сначала.')
        sys.exit(1)
    
    print(f'✅ Тестовый купон: {coupon.code} (кампания: {coupon.campaign.name})')
    
    # Создаем Wallet карту
    print('\n📱 Создание Google Wallet карты...')
    wallet_pass = create_wallet_pass_for_coupon(coupon, platform='google')
    
    if wallet_pass:
        print(f'✅ Wallet карта создана: {wallet_pass.title}')
        print(f'   Object ID: {wallet_pass.object_id}')
        print(f'   Class ID: {wallet_pass.class_id}')
        print(f'   Статус: {wallet_pass.get_status_display()}')
        
        # Генерируем ссылку для сохранения
        print('\n🔗 Генерация ссылки "Save to Google Wallet"...')
        save_link = generate_save_link(wallet_pass)
        
        if save_link:
            print(f'✅ Ссылка сгенерирована успешно!')
            print(f'   Длина ссылки: {len(save_link)} символов')
            print(f'   Домен: {save_link.split("/")[2] if "/" in save_link else "Unknown"}')
            
            # Показываем как использовать
            print('\n🎯 Как протестировать:')
            print('1. Откройте эту ссылку на Android устройстве с тестовым аккаунтом:')
            print(f'   {save_link}')
            print('2. Нажмите "Add to Google Wallet"')
            print('3. Карта появится в Google Wallet приложении')
            print('4. Включите геолокацию и подойдите к указанной точке - появится уведомление')
            
            # Сохраняем ссылку в файл для удобства
            with open('google_wallet_link.txt', 'w') as f:
                f.write(save_link)
            print('\n📁 Ссылка также сохранена в файл google_wallet_link.txt')
            
        else:
            print('❌ Не удалось сгенерировать ссылку')
            print('   Проверьте настройки сервис-аккаунта Google')
    else:
        print('❌ Не удалось создать Wallet карту')
        print('   Возможные причины:')
        print('   • Неверные настройки Google Wallet')
        print('   • Проблемы с сервис-аккаунтом')
        print('   • Нет доступа к Google Wallet API')

except Exception as e:
    print(f'❌ Ошибка демо: {e}')
    import traceback
    traceback.print_exc()

print('\n📋 Следующие шаги:')
print('1. Настройте Google Wallet Console (создайте класс, тест-аккаунты)')
print('2. Добавьте настройки в .env файл')
print('3. Протестируйте на Android устройстве')
print('4. Настройте геолокации для Nearby уведомлений')
print('5. Добавьте Celery таск для expiry уведомлений')

print('\n🔗 Полезные ссылки:')
print('• Google Wallet Console: https://pay.google.com/business/console')
print('• API документация: https://developers.google.com/wallet')
print('• Тестирование: https://developers.google.com/wallet/generic/rest/test-app')
