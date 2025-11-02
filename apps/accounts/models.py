from django.contrib.auth.models import AbstractUser
from django.db import models

class Role(models.TextChoices):
    OWNER = 'owner', 'Owner'
    MANAGER = 'manager', 'Manager'
    CASHIER = 'cashier', 'Cashier'
    ADMIN = 'admin', 'Admin'

class User(AbstractUser):
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.OWNER)
    phone = models.CharField(max_length=30, blank=True)
    locale = models.CharField(max_length=5, default='ru')  # ru/kk

    def is_owner(self): 
        return self.role in {Role.OWNER} or self.is_superuser
    
    def is_manager(self): 
        return self.role in {Role.MANAGER} or self.is_superuser
    
    def is_cashier(self): 
        return self.role in {Role.CASHIER} or self.is_superuser