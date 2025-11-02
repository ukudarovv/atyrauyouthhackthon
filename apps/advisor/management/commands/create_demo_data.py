from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta, datetime
import random
from apps.businesses.models import Business
from apps.customers.models import Customer
from apps.campaigns.models import Campaign
from apps.coupons.models import Coupon
from apps.redemptions.models import Redemption

User = get_user_model()

class Command(BaseCommand):
    help = 'Создает демо данные для тестирования AI Советчика'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Очистить существующие данные перед созданием новых',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('🗑️ Очищаем старые данные...')
            Redemption.objects.all().delete()
            Coupon.objects.all().delete()
            Campaign.objects.all().delete()
            Customer.objects.all().delete()

        # Получаем или создаем пользователя
        user, created = User.objects.get_or_create(
            username='demo_user',
            defaults={
                'email': 'demo@example.com',
                'first_name': 'Demo',
                'last_name': 'User'
            }
        )
        if created:
            user.set_password('demo123')
            user.save()
            self.stdout.write(f'✅ Создан пользователь: {user.username}')

        # Получаем или создаем бизнес
        business, created = Business.objects.get_or_create(
            name='Demo Кафе',
            defaults={
                'owner': user,
                'phone': '+77001234567',
                'address': 'ул. Демонстрационная, 1'
            }
        )
        if created:
            self.stdout.write(f'✅ Создан бизнес: {business.name}')

        # Создаем клиентов (распределяем по времени)
        self.stdout.write('👥 Создаем клиентов...')
        customers_data = []
        
        # За последние 30 дней
        for days_ago in range(30):
            date = timezone.now() - timedelta(days=days_ago)
            # Больше клиентов в последние дни
            num_customers = random.randint(1, max(1, 10 - days_ago // 5))
            
            for i in range(num_customers):
                phone = f'+7700{random.randint(1000000, 9999999)}'
                customer = Customer.objects.create(
                    business=business,
                    phone_e164=phone,
                    first_seen=date,
                    created_at=date
                )
                customers_data.append(customer)

        self.stdout.write(f'✅ Создано {len(customers_data)} клиентов')

        # Создаем кампании
        self.stdout.write('📣 Создаем кампании...')
        campaigns = []
        
        campaign_names = [
            'Скидка 20% на кофе',
            'Акция "Счастливые часы"',
            'Бесплатный десерт',
            'Комбо обед',
            'Скидка постоянным клиентам'
        ]
        
        for i, name in enumerate(campaign_names):
            campaign = Campaign.objects.create(
                business=business,
                name=name,
                is_active=i < 3,  # Первые 3 активные
                created_at=timezone.now() - timedelta(days=random.randint(5, 60))
            )
            campaigns.append(campaign)

        self.stdout.write(f'✅ Создано {len(campaigns)} кампаний')

        # Создаем купоны и погашения
        self.stdout.write('🎟️ Создаем купоны и погашения...')
        
        total_coupons = 0
        total_redemptions = 0
        
        for days_ago in range(30):
            date = timezone.now() - timedelta(days=days_ago)
            
            # Количество купонов в день (больше в последние дни)
            daily_coupons = random.randint(5, max(5, 30 - days_ago))
            
            for _ in range(daily_coupons):
                # Выбираем случайную активную кампанию
                campaign = random.choice(campaigns[:3])  # Только активные
                customer = random.choice(customers_data)
                
                # Создаем купон с уникальным кодом
                code = Coupon.generate_code()
                # Проверяем уникальность кода
                while Coupon.objects.filter(code=code).exists():
                    code = Coupon.generate_code()
                
                coupon = Coupon.objects.create(
                    campaign=campaign,
                    code=code,
                    phone=customer.phone_e164,
                    issued_at=date
                )
                total_coupons += 1
                
                # 60% шанс что купон будет погашен
                if random.random() < 0.6:
                    # Погашение через 0-7 дней после выдачи
                    redeem_date = date + timedelta(
                        hours=random.randint(1, 168)  # 1-168 часов
                    )
                    
                    # Не погашаем в будущем
                    if redeem_date <= timezone.now():
                        # Случайная сумма чека
                        amounts = [500, 750, 1000, 1200, 1500, 2000, 2500, 3000]
                        amount = random.choice(amounts)
                        
                        # Случайное время дня (больше активности 12-14 и 18-20)
                        hour_weights = {
                            8: 1, 9: 2, 10: 3, 11: 4, 12: 8, 13: 10, 14: 8,
                            15: 4, 16: 3, 17: 5, 18: 9, 19: 10, 20: 7, 21: 4, 22: 2
                        }
                        hour = random.choices(
                            list(hour_weights.keys()),
                            weights=list(hour_weights.values())
                        )[0]
                        
                        final_redeem_date = redeem_date.replace(
                            hour=hour,
                            minute=random.randint(0, 59)
                        )
                        
                        Redemption.objects.create(
                            coupon=coupon,
                            cashier=user,
                            amount=amount,
                            redeemed_at=final_redeem_date
                        )
                        total_redemptions += 1

        self.stdout.write(f'✅ Создано {total_coupons} купонов')
        self.stdout.write(f'✅ Создано {total_redemptions} погашений')

        # Статистика
        self.stdout.write('\n📊 СТАТИСТИКА:')
        self.stdout.write(f'👥 Всего клиентов: {Customer.objects.filter(business=business).count()}')
        self.stdout.write(f'📣 Всего кампаний: {Campaign.objects.filter(business=business).count()}')
        self.stdout.write(f'📣 Активных кампаний: {Campaign.objects.filter(business=business, is_active=True).count()}')
        self.stdout.write(f'🎟️ Всего купонов: {Coupon.objects.filter(campaign__business=business).count()}')
        self.stdout.write(f'✅ Всего погашений: {Redemption.objects.filter(coupon__campaign__business=business).count()}')
        
        # Сегодняшняя статистика
        today = timezone.now().date()
        today_customers = Customer.objects.filter(
            business=business,
            first_seen__date=today
        ).count()
        today_coupons = Coupon.objects.filter(
            campaign__business=business,
            issued_at__date=today
        ).count()
        today_redemptions = Redemption.objects.filter(
            coupon__campaign__business=business,
            redeemed_at__date=today
        ).count()
        
        self.stdout.write(f'\n📅 СЕГОДНЯ:')
        self.stdout.write(f'👥 Новых клиентов: {today_customers}')
        self.stdout.write(f'🎟️ Выдано купонов: {today_coupons}')
        self.stdout.write(f'✅ Погашений: {today_redemptions}')
        
        if today_coupons > 0:
            cr = round(today_redemptions / today_coupons * 100, 1)
            self.stdout.write(f'📊 CR: {cr}%')

        self.stdout.write('\n🎉 Демо данные созданы успешно!')
        self.stdout.write('🚀 Теперь можете тестировать AI Советчика: http://192.168.0.40:8000/advisor/chat/')
