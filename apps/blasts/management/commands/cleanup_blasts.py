"""
Management команда для очистки старых данных рассылок
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from apps.blasts.models import DeliveryAttempt, ShortLinkClick, DeliveryStatus


class Command(BaseCommand):
    help = 'Очищает старые данные рассылок'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--delivery-attempts-days',
            type=int,
            default=90,
            help='Удалить попытки доставки старше N дней (по умолчанию: 90)'
        )
        parser.add_argument(
            '--link-clicks-days',
            type=int,
            default=180,
            help='Удалить клики по ссылкам старше N дней (по умолчанию: 180)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать что будет удалено, но не удалять'
        )
    
    def handle(self, *args, **options):
        delivery_days = options['delivery_attempts_days']
        clicks_days = options['link_clicks_days']
        dry_run = options['dry_run']
        
        now = timezone.now()
        
        self.stdout.write(
            self.style.SUCCESS(f'🧹 Очистка данных рассылок {"(тестовый режим)" if dry_run else ""}')
        )
        
        # Очистка старых попыток доставки
        delivery_cutoff = now - timedelta(days=delivery_days)
        
        old_attempts = DeliveryAttempt.objects.filter(
            created_at__lt=delivery_cutoff,
            status__in=[DeliveryStatus.FAILED, DeliveryStatus.BOUNCED]
        )
        
        attempts_count = old_attempts.count()
        
        if attempts_count > 0:
            self.stdout.write(f'📧 Найдено {attempts_count} старых попыток доставки')
            
            if not dry_run:
                deleted_attempts, _ = old_attempts.delete()
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Удалено {deleted_attempts} попыток доставки')
                )
        else:
            self.stdout.write('📧 Старых попыток доставки не найдено')
        
        # Очистка старых кликов по ссылкам
        clicks_cutoff = now - timedelta(days=clicks_days)
        
        old_clicks = ShortLinkClick.objects.filter(
            clicked_at__lt=clicks_cutoff
        )
        
        clicks_count = old_clicks.count()
        
        if clicks_count > 0:
            self.stdout.write(f'🔗 Найдено {clicks_count} старых кликов по ссылкам')
            
            if not dry_run:
                deleted_clicks, _ = old_clicks.delete()
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Удалено {deleted_clicks} кликов')
                )
        else:
            self.stdout.write('🔗 Старых кликов не найдено')
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('⚠️ Тестовый режим - ничего не было удалено')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('🎉 Очистка завершена')
            )
