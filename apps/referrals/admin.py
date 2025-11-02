from django.contrib import admin
from .models import Customer, Referral

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('id','business','phone','email','name','source','created_at')
    list_filter = ('business','source')
    search_fields = ('phone','email','name')

@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ('token','business','referrer','referee','reward_status','created_at')
    list_filter = ('business','reward_status')
    search_fields = ('token','referrer__phone','referee__phone')