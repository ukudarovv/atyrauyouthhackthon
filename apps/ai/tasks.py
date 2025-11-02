from django.utils import timezone
from .models import AIJob, AIJobStatus, AIJobType
from .providers import get_llm
import logging

logger = logging.getLogger(__name__)

# Временная синхронная версия без Celery
def run_ai_job(job_id: int):
    """
    Выполняет AI задачу синхронно (временно без Celery)
    """
    try:
        job = AIJob.objects.get(id=job_id)
        
        # Обновляем статус
        job.status = AIJobStatus.RUNNING
        job.save(update_fields=['status'])
        
        # Получаем провайдер LLM
        llm = get_llm()
        
        logger.info(f"Running AI job {job_id}, type: {job.job_type}")
        logger.info(f"Input data: {job.input_data}")
        
        # Выполняем задачу в зависимости от типа
        if job.job_type == AIJobType.GENERATE_COPY:
            result = llm.generate_copy(job.input_data)
        elif job.job_type == AIJobType.TRANSLATE:
            result = llm.translate(job.input_data)
        else:
            raise ValueError(f"Unknown job type: {job.job_type}")
        
        logger.info(f"AI result: {result}")
        
        # Сохраняем результат (правильное поле!)
        job.output_data = result
        job.status = AIJobStatus.COMPLETED
        job.save(update_fields=['output_data', 'status'])
        
        return {"success": True, "job_id": job_id, "result": result}
        
    except AIJob.DoesNotExist:
        logger.error(f"AI Job {job_id} not found")
        return {"success": False, "error": "Job not found"}
    except Exception as e:
        logger.error(f"AI Job {job_id} failed: {str(e)}")
        # Сохраняем ошибку
        try:
            job.status = AIJobStatus.FAILED
            job.error_message = str(e)
            job.save(update_fields=['status', 'error_message'])
        except:
            pass
        
        return {"success": False, "error": str(e)}
