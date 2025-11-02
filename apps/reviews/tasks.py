import re
import logging
from django.db import transaction
from apps.ai.providers import get_llm
from .models import Review

logger = logging.getLogger(__name__)

def _sanitize(text: str) -> str:
    """Маскируем явные телефоны/email, чтобы не утёкли в LLM"""
    if not text:
        return ""
    
    # Маскируем телефоны
    text = re.sub(r"\b\+?\d[\d\-\s()]{7,}\b", "[phone]", text)
    
    # Маскируем email
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[email]", text)
    
    return text

# Временная синхронная версия без Celery
def analyze_review_task(review_id: int):
    """
    Анализирует отзыв с помощью AI
    В будущем можно сделать асинхронным через Celery: @shared_task(bind=True, max_retries=2)
    """
    try:
        review = Review.objects.get(id=review_id)
        logger.info(f"Starting AI analysis for review {review_id}")
        
        # Получаем AI провайдер
        llm = get_llm()
        
        # Подготавливаем данные для анализа
        payload = {
            "text": _sanitize(review.text),
            "rating": review.rating,
            "locale": "ru"  # В будущем можно определять язык автоматически
        }
        
        logger.info(f"Analyzing review {review_id} with payload: {payload}")
        
        # Выполняем анализ
        result = llm.analyze_review(payload)
        
        logger.info(f"AI analysis result for review {review_id}: {result}")
        
        # Применяем результаты с атомарной транзакцией
        with transaction.atomic():
            # Обновляем поля анализа
            review.ai_sentiment = int(max(-100, min(100, result.get("sentiment", 0))))
            review.ai_labels = result.get("labels", [])[:8]  # Ограничиваем количество тем
            review.ai_toxic = bool(result.get("toxic", False))
            review.ai_summary = (result.get("summary", "") or "")[:280]
            
            # Если отзыв токсичный и был опубликован - скрываем его
            if review.ai_toxic and review.is_published:
                review.is_published = False
                logger.warning(f"Review {review_id} marked as toxic and hidden from public")
            
            # Сохраняем изменения
            review.save(update_fields=[
                "ai_sentiment", "ai_labels", "ai_toxic", "ai_summary", "is_published"
            ])
            
        logger.info(f"Successfully analyzed review {review_id}")
        return {"success": True, "review_id": review_id}
        
    except Review.DoesNotExist:
        logger.error(f"Review {review_id} not found")
        return {"success": False, "error": "Review not found"}
        
    except Exception as e:
        logger.error(f"Failed to analyze review {review_id}: {str(e)}")
        return {"success": False, "error": str(e)}
