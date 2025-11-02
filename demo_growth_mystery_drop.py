#!/usr/bin/env python
"""
Демонстрация Mystery Drop - игровой механики "потряси и получи приз"
"""
import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos_system.settings')
django.setup()

from apps.growth.models import MysteryDrop, MysteryDropTier, MysteryDropAttempt
from apps.growth.services import attempt_mystery_drop
from apps.businesses.models import Business
from apps.accounts.models import User
from apps.campaigns.models import Campaign
from apps.customers.models import Customer
from django.utils import timezone
from datetime import timedelta

print('🎰 Демонстрация Mystery Drop')
print('=' * 50)

def create_mystery_drop_tiers():
    """Создает уровни призов для Mystery Drop"""
    print('\n🎯 Создание уровней призов...')
    
    tiers_data = [
        {'name': 'Скидка 10%', 'discount_percent': 10, 'probability': 40.0, 'emoji': '🎁', 'color': '#4CAF50', 'order': 1},
        {'name': 'Скидка 20%', 'discount_percent': 20, 'probability': 30.0, 'emoji': '🎉', 'color': '#FF9800', 'order': 2},
        {'name': 'Скидка 30%', 'discount_percent': 30, 'probability': 20.0, 'emoji': '⭐', 'color': '#2196F3', 'order': 3},
        {'name': 'Скидка 50%', 'discount_percent': 50, 'probability': 8.0, 'emoji': '🔥', 'color': '#F44336', 'order': 4},
        {'name': 'Бесплатный кофе!', 'discount_percent': 100, 'probability': 2.0, 'emoji': '👑', 'color': '#9C27B0', 'order': 5},
    ]
    
    tiers = []
    for tier_data in tiers_data:
        tier, created = MysteryDropTier.objects.get_or_create(
            name=tier_data['name'],
            defaults=tier_data
        )
        tiers.append(tier)
        if created:
            print(f'   ✅ {tier.emoji} {tier.name} - {tier.probability}% шанс')
        else:
            print(f'   📝 {tier.emoji} {tier.name} - уже существует')
    
    return tiers

def create_mystery_drop_campaign(business, tiers):
    """Создает Mystery Drop для кампании"""
    print(f'\n🎲 Создание Mystery Drop...')
    
    # Находим или создаем кампанию
    campaign, created = Campaign.objects.get_or_create(
        business=business,
        name='Mystery Drop Demo',
        defaults={
            'slug': 'mystery-drop-demo',
            'is_active': True,
            'ends_at': timezone.now() + timedelta(days=30),
            'description': 'Демо кампания для тестирования Mystery Drop механики'
        }
    )
    
    if created:
        print(f'   ✅ Создана кампания: {campaign.name}')
    else:
        print(f'   📝 Кампания уже существует: {campaign.name}')
    
    # Создаем Mystery Drop
    mystery_drop, created = MysteryDrop.objects.get_or_create(
        business=business,
        campaign=campaign,
        defaults={
            'title': '🎰 Потряси и получи скидку!',
            'subtitle': 'Встряхни телефон или поскреби экран',
            'daily_cap_per_phone': 3,
            'daily_cap_total': 1000,
            'scratch_enabled': True,
            'shake_enabled': True,
            'background_color': '#1a1a1a',
            'auto_wallet_creation': True,
            'send_notification': True,
            'enabled': True
        }
    )
    
    if created:
        print(f'   ✅ Создан Mystery Drop: {mystery_drop.title}')
        # Добавляем уровни призов
        mystery_drop.tiers.set(tiers)
        print(f'   ✅ Добавлено {len(tiers)} уровней призов')
    else:
        print(f'   📝 Mystery Drop уже существует: {mystery_drop.title}')
    
    return campaign, mystery_drop

def test_deterministic_selection(mystery_drop):
    """Тестирует детерминированный выбор призов"""
    print(f'\n🧪 Тестирование детерминированного выбора...')
    
    test_phones = ['+77011234567', '+77021234568', '+77031234569', '+77041234570', '+77051234571']
    today = timezone.now().date()
    
    print(f'   📅 Дата: {today}')
    print(f'   📱 Тестируем {len(test_phones)} телефонов...')
    
    results = {}
    for phone in test_phones:
        tier = mystery_drop.pick_tier_deterministic(phone, today)
        if tier:
            results[phone] = tier
            print(f'   {phone[-4:]} → {tier.emoji} {tier.name} ({tier.probability}%)')
        else:
            print(f'   {phone[-4:]} → ❌ Нет приза')
    
    # Проверяем что один телефон всегда получает один приз
    print(f'\n🔄 Проверка консистентности...')
    for phone in test_phones[:2]:  # Тестируем первые 2
        tier1 = mystery_drop.pick_tier_deterministic(phone, today)
        tier2 = mystery_drop.pick_tier_deterministic(phone, today)
        tier3 = mystery_drop.pick_tier_deterministic(phone, today)
        
        if tier1 == tier2 == tier3:
            print(f'   ✅ {phone[-4:]} - консистентный результат: {tier1.name}')
        else:
            print(f'   ❌ {phone[-4:]} - непоследовательный результат!')
    
    return results

def simulate_mystery_attempts(mystery_drop, test_results):
    """Симулирует попытки Mystery Drop"""
    print(f'\n🎮 Симуляция попыток Mystery Drop...')
    
    success_count = 0
    attempts_count = 0
    
    for phone, expected_tier in test_results.items():
        print(f'\n   📱 Телефон: {phone}')
        print(f'   🎯 Ожидаемый приз: {expected_tier.emoji} {expected_tier.name}')
        
        # Делаем попытку
        success, message, data = attempt_mystery_drop(mystery_drop, phone)
        attempts_count += 1
        
        if success:
            success_count += 1
            actual_tier = data['tier']
            print(f'   ✅ Получен: {actual_tier["emoji"]} {actual_tier["name"]} ({actual_tier["discount_percent"]}%)')
            print(f'   🎟️ Код купона: {data["coupon"]["code"]}')
            
            if data.get('wallet_url'):
                print(f'   📱 Wallet URL: {data["wallet_url"]}')
            
            # Проверяем детерминированность
            if actual_tier['name'] == expected_tier.name:
                print(f'   ✅ Детерминированность подтверждена!')
            else:
                print(f'   ⚠️ Расхождение в детерминированности')
        else:
            print(f'   ❌ Ошибка: {message}')
    
    print(f'\n📊 Результаты симуляции:')
    print(f'   Попыток: {attempts_count}')
    print(f'   Успешных: {success_count}')
    print(f'   Процент успеха: {(success_count/attempts_count)*100:.1f}%')
    
    return success_count, attempts_count

def test_daily_limits(mystery_drop):
    """Тестирует дневные лимиты"""
    print(f'\n🚫 Тестирование дневных лимитов...')
    
    test_phone = '+77777777777'
    attempts_made = 0
    
    print(f'   📱 Телефон: {test_phone}')
    print(f'   🎯 Лимит на телефон: {mystery_drop.daily_cap_per_phone} попыток в день')
    
    # Делаем попытки до превышения лимита
    for i in range(mystery_drop.daily_cap_per_phone + 2):
        success, message, data = attempt_mystery_drop(mystery_drop, test_phone)
        attempts_made += 1
        
        if success:
            print(f'   ✅ Попытка {attempts_made}: Успех - {data["tier"]["name"]}')
        else:
            print(f'   ❌ Попытка {attempts_made}: {message}')
            if 'максимум' in message.lower() or 'лимит' in message.lower():
                print(f'   🎯 Лимит сработал после {attempts_made-1} успешных попыток')
                break

def show_mystery_drop_stats(mystery_drop):
    """Показывает статистику Mystery Drop"""
    print(f'\n📈 Статистика Mystery Drop...')
    
    print(f'   📋 Название: {mystery_drop.title}')
    print(f'   🎯 Кампания: {mystery_drop.campaign.name}')
    print(f'   📊 Всего попыток: {mystery_drop.total_attempts}')
    print(f'   🏆 Всего побед: {mystery_drop.total_wins}')
    print(f'   💰 Всего погашений: {mystery_drop.total_redeems}')
    
    if mystery_drop.total_attempts > 0:
        win_rate = (mystery_drop.total_wins / mystery_drop.total_attempts) * 100
        print(f'   📊 Процент побед: {win_rate:.1f}%')
    
    # Статистика по уровням
    print(f'\n🎯 Статистика по уровням призов:')
    for tier in mystery_drop.tiers.all():
        attempts = MysteryDropAttempt.objects.filter(mystery_drop=mystery_drop, tier=tier).count()
        print(f'   {tier.emoji} {tier.name}: {attempts} попыток ({tier.probability}% настроено)')
    
    # Последние попытки
    recent_attempts = MysteryDropAttempt.objects.filter(
        mystery_drop=mystery_drop
    ).order_by('-created_at')[:10]
    
    if recent_attempts:
        print(f'\n📝 Последние попытки:')
        for attempt in recent_attempts:
            status = '🏆' if attempt.won else '❌'
            tier_name = attempt.tier.name if attempt.tier else 'Нет'
            print(f'   {status} {attempt.phone[-4:]} - {tier_name} ({attempt.created_at.strftime("%H:%M:%S")})')

def show_public_url(mystery_drop):
    """Показывает публичную ссылку на Mystery Drop"""
    print(f'\n🌐 Публичная ссылка:')
    print(f'   🔗 http://192.168.0.40:8000/mystery/{mystery_drop.campaign.slug}/')
    print(f'   📱 Откройте на мобильном для тестирования shake-to-reveal')
    print(f'   🖱️ Или используйте мышь для скретч-эффекта')

def main():
    try:
        # Получаем данные для демо
        user = User.objects.filter(role='owner').first()
        if not user:
            print('❌ Нет пользователей с ролью owner')
            return
        
        business = Business.objects.filter(owner=user).first()
        if not business:
            print('❌ Нет бизнесов для демо')
            return
        
        print(f'🏢 Бизнес: {business.name}')
        
        # Создаем уровни призов
        tiers = create_mystery_drop_tiers()
        
        # Создаем Mystery Drop
        campaign, mystery_drop = create_mystery_drop_campaign(business, tiers)
        
        # Тестируем детерминированный выбор
        test_results = test_deterministic_selection(mystery_drop)
        
        # Симулируем попытки
        success_count, attempts_count = simulate_mystery_attempts(mystery_drop, test_results)
        
        # Тестируем лимиты
        test_daily_limits(mystery_drop)
        
        # Показываем статистику
        show_mystery_drop_stats(mystery_drop)
        
        # Показываем публичную ссылку
        show_public_url(mystery_drop)
        
        print(f'\n🎉 Демонстрация Mystery Drop завершена!')
        print(f'\n📋 Что создано:')
        print(f'   • Уровней призов: {len(tiers)}')
        print(f'   • Mystery Drop кампаний: 1')
        print(f'   • Успешных попыток: {success_count}/{attempts_count}')
        
        print(f'\n🚀 Следующие шаги:')
        print(f'1. Откройте админку: http://192.168.0.40:8000/admin/growth/')
        print(f'2. Настройте уровни призов и вероятности')
        print(f'3. Протестируйте на мобильном устройстве')
        print(f'4. Интегрируйте с Google Wallet для автоматических карт')
        print(f'5. Настройте SMS уведомления о выигрышах')
        
    except Exception as e:
        print(f'❌ Ошибка демонстрации: {e}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
