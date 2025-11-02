import logging
from django.core.management.base import BaseCommand
from django.db import models
from apps.reviews.models import Review
from apps.reviews.tasks import analyze_review_task

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Переанализировать отзывы с помощью AI (батчами)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--business_id', 
            type=int,
            help='ID бизнеса для фильтрации отзывов'
        )
        parser.add_argument(
            '--limit', 
            type=int, 
            default=500,
            help='Максимальное количество отзывов для обработки (по умолчанию: 500)'
        )
        parser.add_argument(
            '--force', 
            action='store_true',
            help='Переанализировать даже уже проанализированные отзывы'
        )

    def handle(self, *args, **options):
        business_id = options.get('business_id')
        limit = options.get('limit')
        force = options.get('force')
        
        self.stdout.write(
            self.style.SUCCESS(f'🔍 Начинаем реанализ отзывов (лимит: {limit})')
        )
        
        # Формируем запрос
        queryset = Review.objects.all().order_by('-id')
        
        if business_id:
            queryset = queryset.filter(business_id=business_id)
            self.stdout.write(f'📍 Фильтр по бизнесу ID: {business_id}')
        
        if not force:
            # Только те, что не анализировались или анализ неполный
            queryset = queryset.filter(
                models.Q(ai_sentiment__isnull=True) | 
                models.Q(ai_labels__isnull=True) |
                models.Q(ai_summary='')
            )
            self.stdout.write('⚡ Режим: только неанализированные отзывы')
        else:
            self.stdout.write('🔄 Режим: принудительный реанализ всех')
        
        # Ограничиваем количество
        reviews = queryset[:limit]
        total_count = reviews.count()
        
        if total_count == 0:
            self.stdout.write(
                self.style.WARNING('❌ Отзывы для анализа не найдены')
            )
            return
        
        self.stdout.write(f'📊 Найдено отзывов для анализа: {total_count}')
        
        # Обрабатываем батчами
        success_count = 0
        error_count = 0
        
        for i, review in enumerate(reviews, 1):
            try:
                self.stdout.write(
                    f'🔄 Анализируем отзыв {i}/{total_count} (ID: {review.id})...',
                    ending=''
                )
                
                # Запускаем анализ
                result = analyze_review_task(review.id)
                
                if result.get('success'):
                    success_count += 1
                    self.stdout.write(' ✅')
                else:
                    error_count += 1
                    self.stdout.write(
                        self.style.ERROR(f' ❌ {result.get("error", "Unknown error")}')
                    )
                    
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f' ❌ Ошибка: {str(e)}')
                )
                logger.error(f'Failed to analyze review {review.id}: {str(e)}')
        
        # Итоговая статистика
        self.stdout.write('\n' + '='*50)
        self.stdout.write(
            self.style.SUCCESS(f'✅ Успешно проанализировано: {success_count}')
        )
        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(f'❌ Ошибок: {error_count}')
            )
        
        self.stdout.write(
            self.style.SUCCESS('🎉 Реанализ завершен!')
        )
