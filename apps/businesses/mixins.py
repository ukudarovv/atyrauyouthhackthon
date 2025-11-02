from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from .models import Business

class OwnerQuerysetMixin(LoginRequiredMixin):
    """Фильтрует queryset по owner = request.user."""
    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(owner=self.request.user)

class BusinessContextMixin(LoginRequiredMixin):
    """Проверяет, что current_business выбран; предоставляет self.business."""
    business = None
    
    def dispatch(self, request, *args, **kwargs):
        biz_id = request.session.get('current_business_id')
        if not biz_id:
            return super().dispatch(request, *args, **kwargs)
        self.business = Business.objects.filter(id=biz_id, owner=request.user).first()
        return super().dispatch(request, *args, **kwargs)
