#!/usr/bin/env python
"""
Полная демонстрация омниканальных рассылок
Показывает все возможности системы
"""
import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos_system.settings')
django.setup()

from django.db.models import Count, Q
from apps.blasts.models import *
from apps.blasts.services import *
from apps.blasts.orchestrator import BlastOrchestrator
from apps.businesses.models import Business
from apps.accounts.models import User
from apps.customers.models import Customer
from apps.segments.models import Segment

print('🚀 Полная демонстрация омниканальных рассылок')
print('=' * 60)

def create_test_data():
    """Создает тестовые данные"""
    print('\n📋 Создание тестовых данных...')
    
    # Получаем пользователя и бизнес
    user = User.objects.filter(role='owner').first()
    if not user:
        print('❌ Нет пользователей с ролью owner')
        return None, None
    
    business = Business.objects.filter(owner=user).first()
    if not business:
        print('❌ Нет бизнесов для демо')
        return None, None
    
    # Создаем тестовых клиентов
    customers_data = [
        {'+77011234567': {'first_name': 'Анна', 'email': 'anna@test.com', 'telegram_id': '@anna_test'}},
        {'+77021234567': {'first_name': 'Борис', 'email': 'boris@test.com', 'telegram_id': '@boris_test'}},
        {'+77031234567': {'first_name': 'Виктор', 'email': 'viktor@test.com', 'telegram_id': '@viktor_test'}},
        {'+77041234567': {'first_name': 'Дарья', 'email': 'daria@test.com', 'telegram_id': '@daria_test'}},
        {'+77051234567': {'first_name': 'Елена', 'email': 'elena@test.com', 'telegram_id': '@elena_test'}}
    ]
    
    customers = []
    for phone_data in customers_data:
        for phone, tags in phone_data.items():
            customer, created = Customer.objects.get_or_create(
                business=business,
                phone_e164=phone,
                defaults={'tags': tags}
            )
            customers.append(customer)
            if created:
                print(f'   ✅ Создан клиент: {phone} ({tags["first_name"]})')
    
    return business, customers

def create_contact_points(business, customers):
    """Создает контактные точки для всех каналов"""
    print('\n📞 Создание контактных точек...')
    
    contact_points = []
    
    for customer in customers:
        # SMS
        sms_contact = get_or_create_contact_point(
            business=business,
            customer=customer,
            contact_type='sms',
            value=customer.phone_e164,
            verified=True
        )
        contact_points.append(sms_contact)
        
        # WhatsApp
        wa_contact = get_or_create_contact_point(
            business=business,
            customer=customer,
            contact_type='whatsapp',
            value=customer.phone_e164,
            verified=True
        )
        contact_points.append(wa_contact)
        
        # Email
        email = customer.tags.get('email')
        if email:
            email_contact = get_or_create_contact_point(
                business=business,
                customer=customer,
                contact_type='email',
                value=email,
                verified=True
            )
            contact_points.append(email_contact)
        
        # Telegram
        telegram_id = customer.tags.get('telegram_id')
        if telegram_id:
            tg_contact = get_or_create_contact_point(
                business=business,
                customer=customer,
                contact_type='telegram',
                value=telegram_id,
                verified=True
            )
            contact_points.append(tg_contact)
    
    print(f'   ✅ Создано {len(contact_points)} контактных точек')
    return contact_points

def create_message_templates(business):
    """Создает шаблоны сообщений для разных каналов"""
    print('\n📝 Создание шаблонов сообщений...')
    
    templates = []
    
    # SMS шаблон
    sms_template, created = MessageTemplate.objects.get_or_create(
        business=business,
        name='SMS: Приветственное сообщение',
        channel='sms',
        defaults={
            'locale': 'ru',
            'body_text': 'Привет {{customer_first_name}}! 🎉 Добро пожаловать в {{business_name}}! Ваш код: {{coupon_code}}',
            'variables': ['customer_first_name', 'business_name', 'coupon_code']
        }
    )
    templates.append(sms_template)
    
    # WhatsApp шаблон
    wa_template, created = MessageTemplate.objects.get_or_create(
        business=business,
        name='WhatsApp: Приветственное сообщение',
        channel='whatsapp',
        defaults={
            'locale': 'ru',
            'body_text': '👋 Привет {{customer_first_name}}!\n\n🎉 Добро пожаловать в {{business_name}}!\n\n🎁 Ваш персональный купон: *{{coupon_code}}*\n📅 Действует до: {{coupon_expires_at}}\n\n✨ Используйте его при следующем заказе!',
            'variables': ['customer_first_name', 'business_name', 'coupon_code', 'coupon_expires_at']
        }
    )
    templates.append(wa_template)
    
    # Email шаблон
    email_template, created = MessageTemplate.objects.get_or_create(
        business=business,
        name='Email: Приветственное сообщение',
        channel='email',
        defaults={
            'locale': 'ru',
            'subject': '🎉 Добро пожаловать в {{business_name}}!',
            'body_text': 'Здравствуйте {{customer_first_name}}!\n\nДобро пожаловать в {{business_name}}!\n\nВаш персональный купон: {{coupon_code}}\nДействует до: {{coupon_expires_at}}\n\nИспользуйте его при следующем заказе и получите скидку!\n\nС уважением,\nКоманда {{business_name}}',
            'body_html': '''
            <h1>🎉 Добро пожаловать в {{business_name}}!</h1>
            <p>Здравствуйте <strong>{{customer_first_name}}</strong>!</p>
            <p>Мы рады приветствовать вас в нашем сообществе!</p>
            <div style="background: #f0f9ff; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3>🎁 Ваш персональный купон:</h3>
                <p style="font-size: 24px; font-weight: bold; color: #0066cc;">{{coupon_code}}</p>
                <p>📅 Действует до: <strong>{{coupon_expires_at}}</strong></p>
            </div>
            <p>Используйте его при следующем заказе и получите скидку!</p>
            <p>С уважением,<br/>Команда <strong>{{business_name}}</strong></p>
            ''',
            'variables': ['customer_first_name', 'business_name', 'coupon_code', 'coupon_expires_at']
        }
    )
    templates.append(email_template)
    
    # Telegram шаблон
    tg_template, created = MessageTemplate.objects.get_or_create(
        business=business,
        name='Telegram: Приветственное сообщение',
        channel='telegram',
        defaults={
            'locale': 'ru',
            'body_text': '🤖 Привет {{customer_first_name}}!\n\n🎯 Добро пожаловать в {{business_name}}!\n\n🎟️ Твой купон: `{{coupon_code}}`\n⏰ До: {{coupon_expires_at}}\n\n🚀 Жми /menu чтобы посмотреть наши предложения!',
            'variables': ['customer_first_name', 'business_name', 'coupon_code', 'coupon_expires_at']
        }
    )
    templates.append(tg_template)
    
    print(f'   ✅ Создано {len(templates)} шаблонов сообщений')
    return templates

def create_segments(business, customers):
    """Создает сегменты клиентов"""
    print('\n🎯 Создание сегментов...')
    
    # Все клиенты
    all_segment, created = Segment.objects.get_or_create(
        business=business,
        name='Все клиенты (демо)',
        defaults={
            'slug': 'all-customers-demo',
            'kind': 'custom',
            'definition': {'rules': []},
            'enabled': True
        }
    )
    
    # VIP клиенты (первые 2)
    vip_segment, created = Segment.objects.get_or_create(
        business=business,
        name='VIP клиенты (демо)',
        defaults={
            'slug': 'vip-customers-demo',
            'kind': 'custom',
            'definition': {'rules': [{'field': 'tags__first_name', 'operator': 'in', 'value': ['Анна', 'Борис']}]},
            'enabled': True
        }
    )
    
    # Создаем участников сегментов
    from apps.segments.models import SegmentMember
    
    # Все клиенты
    for customer in customers:
        SegmentMember.objects.get_or_create(
            segment=all_segment,
            customer=customer
        )
    
    # VIP клиенты
    for customer in customers[:2]:
        SegmentMember.objects.get_or_create(
            segment=vip_segment,
            customer=customer
        )
    
    all_segment.size_cached = len(customers)
    all_segment.save()
    
    vip_segment.size_cached = 2
    vip_segment.save()
    
    print(f'   ✅ Создано 2 сегмента: {all_segment.size_cached} + {vip_segment.size_cached} участников')
    return [all_segment, vip_segment]

def create_blast_campaigns(business, segments):
    """Создает различные типы рассылок"""
    print('\n📧 Создание рассылок...')
    
    blasts = []
    
    # 1. Простая рассылка всем
    simple_blast = Blast.objects.create(
        business=business,
        name='Демо: Простая рассылка всем',
        description='Тестовая рассылка для демонстрации базовой функциональности',
        trigger=BlastTrigger.MANUAL,
        segment=segments[0],  # Все клиенты
        strategy={
            'cascade': [
                {'channel': 'sms', 'timeout_min': 0}
            ],
            'stop_on': ['delivered_and_clicked'],
            'quiet_hours': {'start': '21:00', 'end': '09:00', 'timezone': 'Asia/Almaty'},
            'max_cost_per_recipient': 5
        },
        budget_cap=50.0
    )
    blasts.append(simple_blast)
    
    # 2. Каскадная рассылка для VIP
    cascade_blast = Blast.objects.create(
        business=business,
        name='Демо: Каскадная рассылка VIP',
        description='Умная каскадная рассылка с переключением каналов',
        trigger=BlastTrigger.MANUAL,
        segment=segments[1],  # VIP клиенты
        strategy={
            'cascade': [
                {'channel': 'whatsapp', 'timeout_min': 30},
                {'channel': 'sms', 'timeout_min': 60},
                {'channel': 'email', 'timeout_min': 0}
            ],
            'stop_on': ['delivered_and_clicked', 'redeemed'],
            'quiet_hours': {'start': '22:00', 'end': '08:00', 'timezone': 'Asia/Almaty'},
            'max_cost_per_recipient': 15
        },
        budget_cap=100.0
    )
    blasts.append(cascade_blast)
    
    # 3. Мультиканальная рассылка
    multi_blast = Blast.objects.create(
        business=business,
        name='Демо: Мультиканальная рассылка',
        description='Рассылка по всем доступным каналам',
        trigger=BlastTrigger.MANUAL,
        segment=segments[0],  # Все клиенты
        strategy={
            'cascade': [
                {'channel': 'telegram', 'timeout_min': 15},
                {'channel': 'whatsapp', 'timeout_min': 45},
                {'channel': 'sms', 'timeout_min': 120},
                {'channel': 'email', 'timeout_min': 0}
            ],
            'stop_on': ['delivered_and_clicked'],
            'quiet_hours': {'start': '21:00', 'end': '09:00', 'timezone': 'Asia/Almaty'},
            'max_cost_per_recipient': 20
        },
        budget_cap=200.0
    )
    blasts.append(multi_blast)
    
    print(f'   ✅ Создано {len(blasts)} рассылок')
    return blasts

def demonstrate_orchestrator(blasts):
    """Демонстрирует работу оркестратора"""
    print('\n🎭 Демонстрация оркестратора...')
    
    for blast in blasts:
        print(f'\n📧 Рассылка: {blast.name}')
        print(f'   🎯 Сегмент: {blast.segment.name} ({blast.segment.size_cached} чел.)')
        print(f'   💰 Бюджет: ${blast.budget_cap}')
        
        orchestrator = BlastOrchestrator(blast)
        
        # Показываем стратегию
        print(f'   📋 Каскад каналов:')
        for i, step in enumerate(orchestrator.strategy['cascade']):
            timeout_text = f"{step['timeout_min']} мин" if step['timeout_min'] > 0 else "финальный"
            print(f'      {i+1}. {step["channel"]} (timeout: {timeout_text})')
        
        # Создаем получателей
        recipients_count = create_blast_recipients(blast)
        print(f'   👥 Получателей: {recipients_count}')
        
        # Показываем получателей
        recipients = BlastRecipient.objects.filter(blast=blast)[:3]  # Первые 3
        for recipient in recipients:
            customer = recipient.customer
            contact_points = ContactPoint.objects.filter(id__in=recipient.contact_points)
            
            print(f'      📞 {customer.phone_e164} ({customer.tags.get("first_name", "Клиент")})')
            for cp in contact_points:
                print(f'         - {cp.get_type_display()}: {cp.value} {"✅" if cp.verified else "❌"}')

def create_short_links_demo(business, blasts):
    """Демонстрирует короткие ссылки"""
    print('\n🔗 Демонстрация коротких ссылок...')
    
    test_urls = [
        'https://example.com/promo/summer-sale',
        'https://example.com/menu/new-items',
        'https://example.com/locations/nearest'
    ]
    
    short_links = []
    for i, url in enumerate(test_urls):
        short_link = create_short_link(
            business=business,
            original_url=url,
            blast=blasts[i % len(blasts)],
            utm_params={
                'utm_source': 'blast',
                'utm_medium': 'demo',
                'utm_campaign': f'demo-{i+1}'
            }
        )
        short_links.append(short_link)
        
        print(f'   📎 {url[:40]}...')
        print(f'      🔗 {short_link.get_short_url()}')
        print(f'      🔑 Код: {short_link.short_code}')
    
    return short_links

def show_analytics(business, blasts):
    """Показывает аналитику"""
    print('\n📊 Аналитика рассылок...')
    
    # Общая статистика
    total_blasts = Blast.objects.filter(business=business).count()
    total_recipients = BlastRecipient.objects.filter(blast__business=business).count()
    total_attempts = DeliveryAttempt.objects.filter(blast_recipient__blast__business=business).count()
    total_contacts = ContactPoint.objects.filter(business=business).count()
    
    print(f'   📧 Всего рассылок: {total_blasts}')
    print(f'   👥 Всего получателей: {total_recipients}')
    print(f'   📨 Всего попыток доставки: {total_attempts}')
    print(f'   📞 Всего контактных точек: {total_contacts}')
    
    # Статистика по каналам
    print('\n📊 Распределение контактов по каналам:')
    contact_stats = ContactPoint.objects.filter(business=business).values('type').annotate(
        total=Count('id'),
        verified=Count('id', filter=Q(verified=True))
    ).order_by('type')
    
    for stat in contact_stats:
        channel_icon = {
            'email': '📧',
            'sms': '📱',
            'whatsapp': '📱',
            'telegram': '💬',
            'instagram': '📸',
            'wallet': '📱'
        }.get(stat['type'], '📬')
        
        print(f'   {channel_icon} {stat["type"]}: {stat["total"]} всего, {stat["verified"]} проверено')

def main():
    try:
        # Создание тестовых данных
        business, customers = create_test_data()
        if not business:
            return
        
        # Создание контактных точек
        contact_points = create_contact_points(business, customers)
        
        # Создание шаблонов
        templates = create_message_templates(business)
        
        # Создание сегментов
        segments = create_segments(business, customers)
        
        # Создание рассылок
        blasts = create_blast_campaigns(business, segments)
        
        # Демонстрация оркестратора
        demonstrate_orchestrator(blasts)
        
        # Короткие ссылки
        short_links = create_short_links_demo(business, blasts)
        
        # Аналитика
        show_analytics(business, blasts)
        
        print('\n🎉 Демонстрация завершена успешно!')
        print('\n📋 Что создано:')
        print(f'   • Клиентов: {len(customers)}')
        print(f'   • Контактных точек: {len(contact_points)}')
        print(f'   • Шаблонов сообщений: {len(templates)}')
        print(f'   • Сегментов: {len(segments)}')
        print(f'   • Рассылок: {len(blasts)}')
        print(f'   • Коротких ссылок: {len(short_links)}')
        
        print('\n🚀 Следующие шаги:')
        print('1. Откройте /app/blasts/ для управления рассылками')
        print('2. Настройте провайдеров в настройках бизнеса:')
        print('   - SendGrid для Email')
        print('   - Twilio/Infobip для SMS')
        print('   - WhatsApp Business API')
        print('   - Telegram Bot API')
        print('3. Запустите рассылки через веб-интерфейс')
        print('4. Мониторьте аналитику в реальном времени')
        print('5. Настройте webhook\'ы провайдеров:')
        print('   - /webhooks/sendgrid/')
        print('   - /webhooks/twilio/')
        print('   - /webhooks/infobip/')
        print('   - /webhooks/whatsapp/')
        
        print('\n🔧 Управление через команды:')
        print('• python manage.py process_blasts --once  # Одноразовая обработка')
        print('• python manage.py process_blasts --daemon  # Демон режим')
        print('• python manage.py cleanup_blasts  # Очистка старых данных')
        
    except Exception as e:
        print(f'❌ Ошибка демонстрации: {e}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
    
    print('\n🔗 Доступные интерфейсы:')
    print('• 📧 Рассылки: http://192.168.0.40:8000/app/blasts/')
    print('• 📝 Шаблоны: http://192.168.0.40:8000/app/templates/')
    print('• 📞 Контакты: http://192.168.0.40:8000/app/contacts/')
    print('• ⚙️ Админка: http://192.168.0.40:8000/admin/')
    print('• 🔗 Короткие ссылки: http://192.168.0.40:8000/s/{код}/')
    print('• 🔗 Webhook\'ы: http://192.168.0.40:8000/webhooks/{провайдер}/')
