import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Review
from .tasks import analyze_review_task

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Review)
def schedule_review_analysis(sender, instance: Review, created, **kwargs):
    """
    Запускает AI-анализ отзыва при создании или изменении
    """
    # Анализируем при создании или при изменении текста/рейтинга
    should_analyze = False
    
    if created:
        # Новый отзыв - всегда анализируем
        should_analyze = True
        logger.info(f"New review {instance.id} created, scheduling analysis")
    else:
        # Проверяем, изменились ли важные поля
        if hasattr(instance, '_original_text') and instance.text != instance._original_text:
            should_analyze = True
            logger.info(f"Review {instance.id} text changed, scheduling re-analysis")
        elif hasattr(instance, '_original_rating') and instance.rating != instance._original_rating:
            should_analyze = True
            logger.info(f"Review {instance.id} rating changed, scheduling re-analysis")
    
    if should_analyze:
        try:
            # Запускаем анализ (синхронно, в будущем можно сделать асинхронно)
            analyze_review_task(instance.id)
        except Exception as e:
            logger.error(f"Failed to schedule analysis for review {instance.id}: {str(e)}")

@receiver(post_save, sender=Review)
def track_original_values(sender, instance: Review, **kwargs):
    """
    Сохраняем оригинальные значения для отслеживания изменений
    """
    # Сохраняем текущие значения для следующего сравнения
    instance._original_text = instance.text
    instance._original_rating = instance.rating
