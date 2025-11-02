from django.contrib import admin
from .models import Redemption

@admin.register(Redemption)
class RedemptionAdmin(admin.ModelAdmin):
    list_display = ('coupon', 'cashier', 'redeemed_at', 'amount', 'pos_ref')
    search_fields = ('coupon__code', 'pos_ref', 'cashier__username')
    list_filter = ('redeemed_at', 'cashier')
    readonly_fields = ('redeemed_at',)
    date_hierarchy = 'redeemed_at'