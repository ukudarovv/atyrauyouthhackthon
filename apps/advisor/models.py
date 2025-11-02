from django.db import models
from django.contrib.auth import get_user_model
from apps.businesses.models import Business
import uuid

User = get_user_model()

class AdvisorSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='advisor_sessions')
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='advisor_sessions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"Session {self.id} - {self.user.username}"

class AdvisorMessage(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]
    
    session = models.ForeignKey(AdvisorSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.JSONField()  # {"text": "...", "mode": "quick|llm|plan"}
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.role}: {self.content.get('text', '')[:50]}..."
