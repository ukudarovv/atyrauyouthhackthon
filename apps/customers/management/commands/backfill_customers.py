"""
Команда для создания Customer записей из исторических данных
"""
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from apps.coupons.models import Coupon
from apps.redemptions.models import Redemption
from apps.customers.services import upsert_customer_from_issue, upsert_customer_from_redeem
from apps.businesses.models import Business

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Создает Customer записи из исторических данных купонов и погашений"

    def add_arguments(self, parser):
        parser.add_argument(
            '--business_id', 
            type=int, 
            help='ID конкретного бизнеса для обработки'
        )
        parser.add_argument(
            '--limit', 
            type=int, 
            default=10000, 
            help='Максимальное количество записей для обработки'
        )
        parser.add_argument(
            '--batch_size',
            type=int,
            default=100,
            help='Размер батча для обработки'
        )
        parser.add_argument(
            '--skip_coupons',
            action='store_true',
            help='Пропустить обработку купонов'
        )
        parser.add_argument(
            '--skip_redemptions',
            action='store_true',
            help='Пропустить обработку погашений'
        )

    def handle(self, *args, **options):
        start_time = timezone.now()
        
        self.stdout.write(
            self.style.NOTICE('🔄 Начинаем backfill клиентов из исторических данных...')
        )
        
        business_id = options.get('business_id')
        limit = options.get('limit')
        batch_size = options.get('batch_size')
        skip_coupons = options.get('skip_coupons')
        skip_redemptions = options.get('skip_redemptions')
        
        if business_id:
            try:
                business = Business.objects.get(id=business_id)
                self.stdout.write(f'Обрабатываем бизнес: {business.name}')
            except Business.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Бизнес с ID {business_id} не найден')
                )
                return
        else:
            self.stdout.write('Обрабатываем все бизнесы')

        processed_coupons = 0
        processed_redemptions = 0
        
        # Обработка купонов
        if not skip_coupons:
            self.stdout.write('\n📋 Обрабатываем купоны...')
            
            coupons_qs = Coupon.objects.select_related(
                'campaign', 'campaign__business'
            ).order_by('id')
            
            if business_id:
                coupons_qs = coupons_qs.filter(campaign__business_id=business_id)
            
            total_coupons = min(coupons_qs.count(), limit)
            self.stdout.write(f'Найдено купонов для обработки: {total_coupons}')
            
            for i, coupon in enumerate(coupons_qs[:limit]):
                try:
                    customer = upsert_customer_from_issue(coupon)
                    if customer:
                        processed_coupons += 1
                    
                    # Прогресс каждые batch_size записей
                    if (i + 1) % batch_size == 0:
                        self.stdout.write(
                            f'Обработано купонов: {i + 1}/{total_coupons} '
                            f'(успешно: {processed_coupons})'
                        )
                        
                except Exception as e:
                    logger.error(f'Ошибка обработки купона {coupon.id}: {e}')
                    self.stdout.write(
                        self.style.WARNING(f'Ошибка с купоном {coupon.id}: {e}')
                    )
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Обработано купонов: {processed_coupons}')
            )

        # Обработка погашений
        if not skip_redemptions:
            self.stdout.write('\n💰 Обрабатываем погашения...')
            
            redemptions_qs = Redemption.objects.select_related(
                'coupon', 'coupon__campaign', 'coupon__campaign__business'
            ).order_by('id')
            
            if business_id:
                redemptions_qs = redemptions_qs.filter(
                    coupon__campaign__business_id=business_id
                )
            
            total_redemptions = min(redemptions_qs.count(), limit)
            self.stdout.write(f'Найдено погашений для обработки: {total_redemptions}')
            
            for i, redemption in enumerate(redemptions_qs[:limit]):
                try:
                    customer = upsert_customer_from_redeem(redemption)
                    if customer:
                        processed_redemptions += 1
                    
                    # Прогресс каждые batch_size записей
                    if (i + 1) % batch_size == 0:
                        self.stdout.write(
                            f'Обработано погашений: {i + 1}/{total_redemptions} '
                            f'(успешно: {processed_redemptions})'
                        )
                        
                except Exception as e:
                    logger.error(f'Ошибка обработки погашения {redemption.id}: {e}')
                    self.stdout.write(
                        self.style.WARNING(f'Ошибка с погашением {redemption.id}: {e}')
                    )
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Обработано погашений: {processed_redemptions}')
            )

        # Итоговая статистика
        duration = (timezone.now() - start_time).total_seconds()
        
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('🎉 Backfill завершен!'))
        self.stdout.write(f'⏱️  Время выполнения: {duration:.1f} сек')
        self.stdout.write(f'📋 Обработано купонов: {processed_coupons}')
        self.stdout.write(f'💰 Обработано погашений: {processed_redemptions}')
        
        # Показываем статистику по клиентам
        if business_id:
            from apps.customers.services import get_customer_stats
            try:
                business = Business.objects.get(id=business_id)
                stats = get_customer_stats(business)
                self.stdout.write(f'\n📊 Статистика клиентов для {business.name}:')
                self.stdout.write(f'   Всего: {stats["total"]}')
                self.stdout.write(f'   Новые: {stats["new"]}')
                self.stdout.write(f'   Активные: {stats["active"]}')
                self.stdout.write(f'   VIP: {stats["vip"]}')
                self.stdout.write(f'   Риск оттока: {stats["churn_risk"]}')
                self.stdout.write(f'   Спящие: {stats["dormant"]}')
            except Exception as e:
                logger.error(f'Ошибка получения статистики: {e}')
        
        self.stdout.write('\n💡 Рекомендация: запустите пересчет RFM и создание сегментов:')
        if business_id:
            self.stdout.write(f'   python manage.py shell -c "from apps.customers.tasks import rebuild_rfm; rebuild_rfm.delay({business_id})"')
            self.stdout.write(f'   python manage.py shell -c "from apps.segments.tasks import create_system_segments; create_system_segments.delay({business_id})"')
        else:
            self.stdout.write('   python manage.py shell -c "from apps.customers.tasks import rebuild_all_business_rfm; rebuild_all_business_rfm.delay()"')
            self.stdout.write('   python manage.py shell -c "from apps.segments.tasks import nightly_segments_rebuild; nightly_segments_rebuild.delay()"')
