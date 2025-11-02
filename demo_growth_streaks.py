#!/usr/bin/env python
"""
Демонстрация Streaks & Badges - серии посещений с обновлениями в Google Wallet
"""
import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos_system.settings')
django.setup()

from apps.growth.services import update_customer_streak
from apps.growth.tasks import update_wallet_streak_task, send_streak_milestone_notification_task, run_sync_fallback
from apps.businesses.models import Business
from apps.accounts.models import User
from apps.campaigns.models import Campaign
from apps.customers.models import Customer
from apps.coupons.models import Coupon
from apps.redemptions.models import Redemption
from apps.wallet.models import WalletPass
from django.utils import timezone
from datetime import timedelta, datetime

print('🔥 Демонстрация Streaks & Badges')
print('=' * 50)

def create_test_customers_with_wallet(business):
    """Создает тестовых клиентов с Wallet картами"""
    print('\n👥 Создание тестовых клиентов с Wallet картами...')
    
    customers_data = [
        {'+77011111111': {'first_name': 'Анна', 'streak_scenario': 'new_customer'}},
        {'+77022222222': {'first_name': 'Борис', 'streak_scenario': 'returning_customer'}},
        {'+77033333333': {'first_name': 'Виктор', 'streak_scenario': 'streak_master'}},
        {'+77044444444': {'first_name': 'Галина', 'streak_scenario': 'casual_visitor'}},
    ]
    
    customers = []
    for phone_data in customers_data:
        for phone, info in phone_data.items():
            customer, created = Customer.objects.get_or_create(
                business=business,
                phone_e164=phone,
                defaults={
                    'tags': info,
                    'streak_count': 0,
                    'streak_best': 0,
                    'last_redeem_date': None
                }
            )
            customers.append(customer)
            
            if created:
                print(f'   ✅ Создан клиент: {phone} ({info["first_name"]})')
            else:
                print(f'   📝 Клиент существует: {phone} ({info["first_name"]})')
    
    return customers

def create_wallet_passes_for_customers(business, customers):
    """Создает Wallet карты для клиентов"""
    print('\n📱 Создание Wallet карт для клиентов...')
    
    # Находим или создаем кампанию
    campaign, created = Campaign.objects.get_or_create(
        business=business,
        name='Streaks Demo Campaign',
        defaults={
            'slug': 'streaks-demo',
            'is_active': True,
            'description': 'Демо кампания для тестирования серий посещений'
        }
    )
    
    wallet_passes = []
    for i, customer in enumerate(customers):
        # Создаем купон для каждого клиента (используем уникальный метаданные)
        coupon, created = Coupon.objects.get_or_create(
            campaign=campaign,
            phone=customer.phone_e164,
            metadata__source='streaks_demo',
            defaults={
                'code': Coupon.generate_code(),
                'metadata': {'source': 'streaks_demo', 'customer_id': customer.id}
            }
        )
        
        # Создаем Wallet карту
        wallet_pass, created = WalletPass.objects.get_or_create(
            business=business,
            coupon=coupon,
            customer_phone=customer.phone_e164,
            defaults={
                'platform': 'google',
                'class_id': f'{business.id}_streaks_demo',
                'object_id': f'{business.id}_streaks_{customer.id}_{coupon.id}',
                'title': f'Карта лояльности - {customer.tags.get("first_name", "Клиент")}',
                'barcode_value': coupon.code,
                'status': 'active',
                'streak_data': {}
            }
        )
        
        wallet_passes.append(wallet_pass)
        
        if created:
            print(f'   ✅ Создана Wallet карта: {customer.phone_e164} (ID: {wallet_pass.object_id})')
        else:
            print(f'   📝 Wallet карта существует: {customer.phone_e164}')
    
    return campaign, wallet_passes

def simulate_redemption_streaks(customers, campaign):
    """Симулирует погашения для создания серий"""
    print('\n🎯 Симуляция погашений для создания серий...')
    
    scenarios = {
        'new_customer': [0],  # Первое посещение
        'returning_customer': [0, 1, 3],  # Посещения с перерывом
        'streak_master': [0, 1, 2, 3, 4, 5, 6],  # Ежедневные посещения
        'casual_visitor': [0, 10],  # Редкие посещения
    }
    
    redemptions = []
    now = timezone.now()
    
    for customer in customers:
        scenario = customer.tags.get('streak_scenario', 'new_customer')
        visit_days = scenarios.get(scenario, [0])
        
        print(f'\n   👤 {customer.tags.get("first_name")} ({customer.phone_e164}):')
        print(f'      📋 Сценарий: {scenario}')
        print(f'      📅 Дни посещений: {visit_days}')
        
        for day_offset in visit_days:
            redeem_date = now - timedelta(days=len(visit_days) - day_offset - 1)
            
            # Создаем купон для погашения
            coupon = Coupon.objects.create(
                campaign=campaign,
                phone=customer.phone_e164,
                code=Coupon.generate_code(),
                metadata={'source': 'streak_simulation', 'day': day_offset}
            )
            
            # Создаем погашение (нужен кассир)
            user = User.objects.filter(role='owner').first()
            redemption = Redemption.objects.create(
                coupon=coupon,
                cashier=user
            )
            # Обновляем время погашения
            redemption.redeemed_at = redeem_date
            redemption.save()
            
            redemptions.append(redemption)
            
            # Обновляем серию клиента
            streak_data = update_customer_streak(customer, redeem_date)
            
            print(f'      📅 День {day_offset}: Серия {streak_data["current_streak"]} {"🆕" if streak_data["is_new_record"] else ""}')
            
            # Обновляем Wallet карту
            run_sync_fallback(update_wallet_streak_task, customer.id, streak_data)
            
            # Отправляем уведомление о milestone
            if streak_data['current_streak'] in [3, 5, 10]:
                run_sync_fallback(send_streak_milestone_notification_task, customer.id, streak_data['current_streak'])
    
    return redemptions

def show_streak_statistics(customers):
    """Показывает статистику серий"""
    print('\n📊 Статистика серий посещений:')
    
    for customer in customers:
        customer.refresh_from_db()  # Обновляем данные из БД
        
        name = customer.tags.get('first_name', 'Клиент')
        current = customer.streak_count
        best = customer.streak_best
        last_date = customer.last_redeem_date
        
        # Определяем статус серии
        if current == 0:
            status = "🆕 Новичок"
        elif current >= 7:
            status = "🏆 Мастер серий"
        elif current >= 5:
            status = "🔥 Горячая серия"
        elif current >= 3:
            status = "⭐ Хорошая серия"
        else:
            status = "📈 Начинающий"
        
        print(f'   👤 {name} ({customer.phone_e164[-4:]}):')
        print(f'      🔥 Текущая серия: {current}')
        print(f'      🏆 Лучшая серия: {best}')
        print(f'      📅 Последнее посещение: {last_date or "Никогда"}')
        print(f'      🎯 Статус: {status}')
        
        # Показываем данные Wallet карты
        wallet_pass = WalletPass.objects.filter(customer_phone=customer.phone_e164).first()
        if wallet_pass and wallet_pass.streak_data:
            print(f'      📱 Wallet данные: {wallet_pass.streak_data}')
        
        print()

def show_streak_distribution(business):
    """Показывает распределение клиентов по сериям"""
    print('\n📈 Распределение клиентов по длине серий:')
    
    from django.db.models import Count, Q
    
    streak_ranges = [
        (0, 0, "🆕 Новички"),
        (1, 2, "📈 Начинающие"),
        (3, 4, "⭐ Хорошие"),
        (5, 6, "🔥 Горячие"),
        (7, 999, "🏆 Мастера")
    ]
    
    total_customers = Customer.objects.filter(business=business).count()
    
    for min_streak, max_streak, label in streak_ranges:
        if max_streak == 999:
            count = Customer.objects.filter(
                business=business,
                streak_count__gte=min_streak
            ).count()
        else:
            count = Customer.objects.filter(
                business=business,
                streak_count__gte=min_streak,
                streak_count__lte=max_streak
            ).count()
        
        percentage = (count / total_customers * 100) if total_customers > 0 else 0
        print(f'   {label}: {count} клиентов ({percentage:.1f}%)')

def demonstrate_wallet_updates():
    """Демонстрирует обновления Wallet карт"""
    print('\n📱 Демонстрация обновлений Google Wallet:')
    
    print('   ✅ Wallet карты автоматически обновляются при каждом погашении')
    print('   🔥 Серии 5+ получают золотой цвет фона')
    print('   📊 Прогресс серий отображается в текстовых модулях')
    print('   🔔 Нативные пуши отправляются при достижении milestone')
    
    print('\n📋 Формат обновлений Wallet:')
    print('   • textModulesData: Счетчик серий с эмодзи')
    print('   • hexBackgroundColor: Золотой для рекордов')
    print('   • state: active для всех активных карт')
    
    print('\n🎯 Milestone уведомления:')
    milestones = [3, 5, 10, 15, 20, 25, 30]
    for milestone in milestones:
        if milestone == 3:
            message = "🎉 3 визита подряд! Особый сюрприз ждет!"
        elif milestone == 5:
            message = "🔥 5 визитов! VIP статус активирован!"
        elif milestone == 10:
            message = "👑 10 визитов! Зал славы!"
        else:
            message = f"⭐ {milestone} визитов подряд!"
        
        print(f'   {milestone}: {message}')

def show_integration_points():
    """Показывает точки интеграции"""
    print('\n🔗 Точки интеграции Streaks:')
    
    print('   1. 📱 Google Wallet PATCH API:')
    print('      • update_wallet_object() в gw_client.py')
    print('      • Обновление textModulesData и hexBackgroundColor')
    print('      • Автоматические нативные пуши от Android/iOS')
    
    print('   2. 🎯 Django Signals:')
    print('      • post_save на Redemption → update_customer_streak')
    print('      • Автоматический расчет серий при каждом погашении')
    
    print('   3. 📊 Celery Tasks:')
    print('      • update_wallet_streak_task - обновление карт')
    print('      • send_streak_milestone_notification_task - уведомления')
    
    print('   4. 🏆 Business Logic:')
    print('      • Серия прерывается если >7 дней между визитами')
    print('      • Лучшая серия сохраняется отдельно')
    print('      • Milestone уведомления на важных достижениях')

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
        
        # Создаем тестовых клиентов
        customers = create_test_customers_with_wallet(business)
        
        # Создаем Wallet карты
        campaign, wallet_passes = create_wallet_passes_for_customers(business, customers)
        
        # Симулируем погашения для серий
        redemptions = simulate_redemption_streaks(customers, campaign)
        
        # Показываем статистику
        show_streak_statistics(customers)
        
        # Показываем распределение
        show_streak_distribution(business)
        
        # Демонстрируем обновления Wallet
        demonstrate_wallet_updates()
        
        # Показываем точки интеграции
        show_integration_points()
        
        print(f'\n🎉 Демонстрация Streaks завершена!')
        print(f'\n📋 Что создано:')
        print(f'   • Клиентов с сериями: {len(customers)}')
        print(f'   • Wallet карт: {len(wallet_passes)}')
        print(f'   • Симулированных погашений: {len(redemptions)}')
        
        # Показываем итоговую статистику
        total_streaks = sum(c.streak_count for c in customers)
        max_streak = max((c.streak_count for c in customers), default=0)
        avg_streak = total_streaks / len(customers) if customers else 0
        
        print(f'   • Общая сумма серий: {total_streaks}')
        print(f'   • Максимальная серия: {max_streak}')
        print(f'   • Средняя серия: {avg_streak:.1f}')
        
        print(f'\n🚀 Следующие шаги:')
        print(f'1. Откройте админку: http://192.168.0.40:8000/admin/customers/customer/')
        print(f'2. Проверьте поля streak_count и streak_best')
        print(f'3. Посмотрите Wallet карты: http://192.168.0.40:8000/admin/wallet/walletpass/')
        print(f'4. Настройте Google Wallet API для реальных обновлений')
        print(f'5. Протестируйте на реальных погашениях')
        
        print(f'\n🔥 Streaks UI:')
        print(f'• Обзор серий: http://192.168.0.40:8000/app/growth/streaks/')
        print(f'• Аналитика Growth: http://192.168.0.40:8000/app/growth/analytics/')
        
    except Exception as e:
        print(f'❌ Ошибка демонстрации: {e}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
