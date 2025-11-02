"""
Management команда для обработки рассылок (альтернатива Celery Beat)
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import time
import logging

from apps.blasts.orchestrator import process_all_pending_blasts, process_scheduled_blasts

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Обрабатывает рассылки в фоновом режиме'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=60,
            help='Интервал обработки в секундах (по умолчанию: 60)'
        )
        parser.add_argument(
            '--once',
            action='store_true',
            help='Запустить только один раз, без цикла'
        )
        parser.add_argument(
            '--daemon',
            action='store_true',
            help='Запустить как демон (бесконечный цикл)'
        )
    
    def handle(self, *args, **options):
        interval = options['interval']
        run_once = options['once']
        daemon_mode = options['daemon']
        
        self.stdout.write(
            self.style.SUCCESS(f'🚀 Запуск обработчика рассылок (интервал: {interval}с)')
        )
        
        if run_once:
            self._process_once()
        elif daemon_mode:
            self._run_daemon(interval)
        else:
            self._run_with_timeout(interval)
    
    def _process_once(self):
        """Однократная обработка"""
        try:
            self.stdout.write('📧 Обрабатываем запланированные рассылки...')
            process_scheduled_blasts()
            
            self.stdout.write('🔄 Обрабатываем активные рассылки...')
            process_all_pending_blasts()
            
            self.stdout.write(self.style.SUCCESS('✅ Обработка завершена'))
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Ошибка обработки: {e}')
            )
            logger.error(f'Error in blast processing: {e}')
    
    def _run_daemon(self, interval):
        """Запуск в режиме демона"""
        self.stdout.write(f'🔄 Запуск в режиме демона (каждые {interval}с)')
        
        try:
            while True:
                start_time = time.time()
                
                self._process_once()
                
                # Вычисляем время следующего запуска
                elapsed = time.time() - start_time
                sleep_time = max(0, interval - elapsed)
                
                if sleep_time > 0:
                    self.stdout.write(f'💤 Ожидание {sleep_time:.1f}с до следующей обработки...')
                    time.sleep(sleep_time)
                
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS('\n🛑 Остановлено пользователем'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Критическая ошибка: {e}'))
            logger.error(f'Critical error in daemon mode: {e}')
    
    def _run_with_timeout(self, interval):
        """Запуск с таймаутом (для cron)"""
        max_runtime = 300  # 5 минут максимум
        start_time = time.time()
        
        self.stdout.write(f'⏰ Запуск с таймаутом {max_runtime}с')
        
        try:
            while time.time() - start_time < max_runtime:
                self._process_once()
                
                # Проверяем есть ли еще работа
                from apps.blasts.models import Blast, BlastStatus
                active_blasts = Blast.objects.filter(status=BlastStatus.RUNNING).count()
                
                if active_blasts == 0:
                    self.stdout.write('✅ Нет активных рассылок, завершаем')
                    break
                
                self.stdout.write(f'🔄 Активных рассылок: {active_blasts}, ждем {interval}с...')
                time.sleep(interval)
            
            self.stdout.write(self.style.SUCCESS('⏰ Таймаут достигнут, завершаем'))
            
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS('\n🛑 Остановлено пользователем'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Ошибка: {e}'))
            logger.error(f'Error in timed processing: {e}')
