"""
Celery задачи для обработки клиентов и RFM анализа
"""
import logging
from celery import shared_task
from django.utils import timezone
from apps.businesses.models import Business
from .services import calculate_rfm_scores

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2)
def rebuild_rfm(self, business_id: int):
    """
    Пересчитывает RFM метрики для всех клиентов бизнеса
    """
    try:
        business = Business.objects.get(id=business_id)
        logger.info(f"Starting RFM rebuild for business {business.name} (ID: {business_id})")
        
        start_time = timezone.now()
        calculate_rfm_scores(business)
        duration = (timezone.now() - start_time).total_seconds()
        
        logger.info(f"RFM rebuild completed for business {business_id} in {duration:.2f}s")
        
    except Business.DoesNotExist:
        logger.error(f"Business {business_id} not found")
        raise
    except Exception as e:
        logger.error(f"Error rebuilding RFM for business {business_id}: {e}")
        self.retry(exc=e, countdown=60)


@shared_task
def rebuild_all_business_rfm():
    """
    Пересчитывает RFM для всех бизнесов (ночная задача)
    """
    logger.info("Starting RFM rebuild for all businesses")
    
    businesses = Business.objects.all()
    total_count = businesses.count()
    
    for i, business in enumerate(businesses.iterator(), 1):
        try:
            logger.info(f"Processing business {i}/{total_count}: {business.name}")
            rebuild_rfm.delay(business.id)
        except Exception as e:
            logger.error(f"Error queuing RFM rebuild for business {business.id}: {e}")
    
    logger.info(f"Queued RFM rebuild for {total_count} businesses")
