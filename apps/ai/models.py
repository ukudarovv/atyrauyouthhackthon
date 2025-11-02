from django.db import models
from django.conf import settings
from apps.campaigns.models import Campaign

User = settings.AUTH_USER_MODEL

class AIJobStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    RUNNING = 'running', 'Running'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'

class AIJobType(models.TextChoices):
    GENERATE_COPY = 'generate_copy', 'Generate Copy'
    TRANSLATE = 'translate', 'Translate'

class AIJob(models.Model):
    """
    Задача для AI-обработки (копирайтинг, перевод и т.д.)
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_jobs')
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='ai_jobs', null=True, blank=True)
    
    job_type = models.CharField(max_length=32, choices=AIJobType.choices)
    status = models.CharField(max_length=16, choices=AIJobStatus.choices, default=AIJobStatus.PENDING)
    
    # Входные данные (JSON)
    input_data = models.JSONField(default=dict)
    
    # Результат (JSON)
    output_data = models.JSONField(default=dict, blank=True)
    
    # Ошибки
    error_message = models.TextField(blank=True)
    
    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['campaign', 'job_type']),
        ]
    
    def __str__(self):
        return f"{self.get_job_type_display()} - {self.get_status_display()}"
