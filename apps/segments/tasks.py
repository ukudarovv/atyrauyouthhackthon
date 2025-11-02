"""
Celery задачи для перестроения сегментов
"""
import logging
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from apps.businesses.models import Business
from .models import Segment, SegmentMember, SYSTEM_SEGMENTS, SegmentKind
from .services import build_queryset, mask_phone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2)
def rebuild_segment(self, segment_id: int):
    """
    Перестраивает конкретный сегмент
    """
    try:
        segment = Segment.objects.select_related('business').get(
            id=segment_id, 
            enabled=True
        )
        
        logger.info(f"Rebuilding segment {segment.name} (ID: {segment_id})")
        start_time = timezone.now()
        
        # Строим QuerySet на основе правил
        customers_qs = build_queryset(segment.business, segment.definition)
        
        with transaction.atomic():
            # Для динамических сегментов заменяем всех участников
            if segment.is_dynamic:
                SegmentMember.objects.filter(segment=segment).delete()
            
            # Получаем клиентов (лимит 50000 для безопасности)
            customers = list(customers_qs.only('id')[:50000])
            
            # Батчевая вставка участников
            members_to_create = [
                SegmentMember(segment=segment, customer=customer)
                for customer in customers
            ]
            
            SegmentMember.objects.bulk_create(
                members_to_create, 
                ignore_conflicts=True,
                batch_size=1000
            )
            
            # Обновляем статистику сегмента
            segment.size_cached = len(customers)
            
            # Создаем превью (первые 5 телефонов, маскированных)
            sample_phones = list(
                customers_qs.values_list('phone_e164', flat=True)[:5]
            )
            segment.preview = [mask_phone(phone) for phone in sample_phones]
            
            segment.last_built_at = timezone.now()
            segment.save(update_fields=[
                'size_cached', 'preview', 'last_built_at'
            ])
        
        duration = (timezone.now() - start_time).total_seconds()
        logger.info(
            f"Segment {segment.name} rebuilt successfully: "
            f"{segment.size_cached} members in {duration:.2f}s"
        )
        
    except Segment.DoesNotExist:
        logger.error(f"Segment {segment_id} not found or disabled")
        raise
    except Exception as e:
        logger.error(f"Error rebuilding segment {segment_id}: {e}")
        self.retry(exc=e, countdown=60)


@shared_task
def rebuild_all_segments(business_id: int):
    """
    Перестраивает все активные сегменты бизнеса
    """
    try:
        business = Business.objects.get(id=business_id)
        logger.info(f"Rebuilding all segments for business {business.name}")
        
        segments = Segment.objects.filter(
            business=business,
            enabled=True
        )
        
        total_segments = segments.count()
        logger.info(f"Found {total_segments} segments to rebuild")
        
        for segment in segments.iterator():
            try:
                rebuild_segment.delay(segment.id)
            except Exception as e:
                logger.error(f"Error queuing rebuild for segment {segment.id}: {e}")
        
        logger.info(f"Queued rebuild for {total_segments} segments")
        
    except Business.DoesNotExist:
        logger.error(f"Business {business_id} not found")
        raise
    except Exception as e:
        logger.error(f"Error rebuilding segments for business {business_id}: {e}")
        raise


@shared_task
def create_system_segments(business_id: int):
    """
    Создает системные сегменты для бизнеса
    """
    try:
        business = Business.objects.get(id=business_id)
        logger.info(f"Creating system segments for business {business.name}")
        
        created_count = 0
        
        for slug, config in SYSTEM_SEGMENTS.items():
            segment, created = Segment.objects.get_or_create(
                business=business,
                slug=slug,
                defaults={
                    'name': config['name'],
                    'kind': SegmentKind.SYSTEM,
                    'description': config['description'],
                    'color': config['color'],
                    'definition': config['definition'],
                    'is_dynamic': True,
                    'enabled': True
                }
            )
            
            if created:
                created_count += 1
                # Сразу запускаем перестроение
                rebuild_segment.delay(segment.id)
                logger.info(f"Created system segment: {segment.name}")
        
        logger.info(f"Created {created_count} new system segments")
        return created_count
        
    except Business.DoesNotExist:
        logger.error(f"Business {business_id} not found")
        raise
    except Exception as e:
        logger.error(f"Error creating system segments for business {business_id}: {e}")
        raise


@shared_task
def nightly_segments_rebuild():
    """
    Ночное перестроение всех сегментов
    """
    logger.info("Starting nightly segments rebuild")
    
    businesses = Business.objects.all()
    total_businesses = businesses.count()
    
    for i, business in enumerate(businesses.iterator(), 1):
        try:
            logger.info(f"Processing business {i}/{total_businesses}: {business.name}")
            
            # Сначала пересчитываем RFM
            from apps.customers.tasks import rebuild_rfm
            rebuild_rfm.delay(business.id)
            
            # Затем перестраиваем сегменты (с задержкой)
            rebuild_all_segments.apply_async(
                args=[business.id],
                countdown=300  # 5 минут задержки для завершения RFM
            )
            
        except Exception as e:
            logger.error(f"Error processing business {business.id}: {e}")
    
    logger.info(f"Queued nightly rebuild for {total_businesses} businesses")
