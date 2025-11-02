from django.db import transaction
from django.utils import timezone
from .models import Customer, Referral, RewardStatus, CustomerSource

def get_or_create_customer(business, *, phone:str|None=None, email:str|None=None, source=CustomerSource.LANDING, name:str=''):
    assert phone or email, "Нужен phone или email"
    qs = Customer.objects.filter(business=business)
    if phone:
        c = qs.filter(phone=phone).first()
    else:
        c = qs.filter(email=email).first()
    if c:
        # мягкое обновление источника/имени
        updated = False
        if name and not c.name:
            c.name = name; updated = True
        if source and c.source == CustomerSource.LANDING and source != CustomerSource.LANDING:
            c.source = source; updated = True
        if updated: c.save(update_fields=['name','source'])
        return c
    return Customer.objects.create(business=business, phone=phone or '', email=email or '', source=source, name=name)

def attach_referral_if_present(request, *, business, referee_customer):
    """Если в сессии есть ref_token — связать его с текущим клиентом (если не self-ref)."""
    token = request.session.get('ref_token')
    if not token: return None
    ref = Referral.objects.filter(token=token, business=business).first()
    if not ref: return None
    if ref.referrer_id == referee_customer.id:
        # самореферал не засчитываем
        return None
    if not ref.referee_id:
        ref.referee = referee_customer
        ref.reward_status = RewardStatus.PENDING
        ref.save(update_fields=['referee','reward_status'])
    return ref

def grant_referral_if_applicable(*, business, referee_customer):
    """Когда друг реально пришёл (погашение), переводим награду в GRANTED."""
    ref = Referral.objects.filter(business=business, referee=referee_customer, reward_status=RewardStatus.PENDING).first()
    if ref:
        ref.reward_status = RewardStatus.GRANTED
        ref.save(update_fields=['reward_status'])
    return ref

def create_referral_for_referrer(*, business, referrer_customer):
    token = Referral.gen_token()
    while Referral.objects.filter(token=token).exists():
        token = Referral.gen_token()
    return Referral.objects.create(business=business, referrer=referrer_customer, token=token)
