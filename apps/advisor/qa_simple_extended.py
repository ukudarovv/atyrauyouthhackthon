import re
from dataclasses import dataclass
from typing import Optional, Tuple
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Count, Q, F, Avg
import pytz
from apps.customers.models import Customer
from apps.coupons.models import Coupon
from apps.redemptions.models import Redemption
from apps.campaigns.models import Campaign

# опционально — если уже есть такие модели; иначе закомментируйте импорты и хендлеры
try:
    from apps.wallet.models import WalletPass  # содержит customer/object_id/created_at/status
except Exception:
    WalletPass = None
try:
    from apps.blasts.models import DeliveryAttempt  # содержит channel/status/created_at/result
except Exception:
    DeliveryAttempt = None
try:
    from apps.referrals.models import Referral
except Exception:
    Referral = None

DEFAULT_TZ = "Asia/Atyrau"

@dataclass
class QAResult:
    text: str

# ---------- период ----------
def _period_bounds(q: str, tzname: str) -> Tuple[datetime, datetime, str]:
    tz = pytz.timezone(tzname)
    now = timezone.now().astimezone(tz)
    today = now.date()
    qn = q.lower()

    # "за X дней" (например, "за 30 дней")
    m = re.search(r"за\s+(\d{1,3})\s*д(ней|ня|н)", qn)
    if m:
        days = int(m.group(1))
        start_d = today - timedelta(days=days - 1)
        start = tz.localize(datetime.combine(start_d, datetime.min.time()))
        end = tz.localize(datetime.combine(today, datetime.max.time()))
        return start, end, f"за {days} дн."

    if "вчера" in qn or "yesterday" in qn:
        d = today - timedelta(days=1)
        start = tz.localize(datetime.combine(d, datetime.min.time()))
        end = tz.localize(datetime.combine(d, datetime.max.time()))
        return start, end, "вчера"

    if any(w in qn for w in ["эта неделя", "на этой неделе"]):
        weekday = today.weekday()  # 0 Mon
        start_d = today - timedelta(days=weekday)
        start = tz.localize(datetime.combine(start_d, datetime.min.time()))
        end = tz.localize(datetime.combine(today, datetime.max.time()))
        return start, end, "эта неделя"

    if any(w in qn for w in ["этот месяц", "в этом месяце"]):
        start_d = today.replace(day=1)
        start = tz.localize(datetime.combine(start_d, datetime.min.time()))
        end = tz.localize(datetime.combine(today, datetime.max.time()))
        return start, end, "этот месяц"

    # по умолчанию — сегодня
    start = tz.localize(datetime.combine(today, datetime.min.time()))
    end = tz.localize(datetime.combine(today, datetime.max.time()))
    return start, end, "сегодня"

# ---------- хендлеры ----------
def _new_customers(business, q, tz) -> Optional[QAResult]:
    if not re.search(r"(сколько|ск)\s+.*(нов)[^\n]*клиент", q.lower()):
        return None
    start, end, label = _period_bounds(q, tz)
    # Используем created_at как основной источник, first_seen как дополнительный
    cnt = Customer.objects.filter(business=business, created_at__gte=start, created_at__lte=end).count()
    if cnt == 0:
        cnt = Customer.objects.filter(business=business, first_seen__gte=start, first_seen__lte=end).count()
    return QAResult(f"🧾 Новых клиентов {label}: **{cnt}**.")

def _issues(business, q, tz) -> Optional[QAResult]:
    if not re.search(r"(сколько|ск)\s+.*(выдано|выдач|куп|issues?)", q.lower()):
        return None
    start, end, label = _period_bounds(q, tz)
    cnt = Coupon.objects.filter(campaign__business=business, issued_at__gte=start, issued_at__lte=end).count()
    return QAResult(f"🎟️ Выдач купонов {label}: **{cnt}**.")

def _redeems(business, q, tz) -> Optional[QAResult]:
    if not re.search(r"(сколько|ск)\s+.*(погашен|редемп|redeem)", q.lower()):
        return None
    start, end, label = _period_bounds(q, tz)
    cnt = Redemption.objects.filter(coupon__campaign__business=business, redeemed_at__gte=start, redeemed_at__lte=end).count()
    return QAResult(f"✅ Погашений {label}: **{cnt}**.")

def _cr_today(business, q, tz) -> Optional[QAResult]:
    if not re.search(r"(cr|конверси|коэффиц)[^\n]*(issue.?redeem|выдач.*в погашен|сегодня|вчера|неделя|месяц)", q.lower()):
        return None
    start, end, label = _period_bounds(q, tz)
    issues = Coupon.objects.filter(campaign__business=business, issued_at__gte=start, issued_at__lte=end).count()
    redeems = Redemption.objects.filter(coupon__campaign__business=business, redeemed_at__gte=start, redeemed_at__lte=end).count()
    cr = round((redeems / issues * 100), 1) if issues else 0.0
    return QAResult(f"📈 CR issue→redeem {label}: **{cr}%** (выдач {issues}, погашений {redeems}).")

def _active_campaigns(business, q, tz) -> Optional[QAResult]:
    if not re.search(r"(сколько|ск)\s+.*активн[^\n]*кампан", q.lower()):
        return None
    cnt = Campaign.objects.filter(business=business, is_active=True).count()
    return QAResult(f"📣 Активных кампаний: **{cnt}**.")

def _total_customers(business, q, tz) -> Optional[QAResult]:
    if not re.search(r"(сколько|ск|количество)\s+.*(всего|общ|итого|всех)[^\n]*(клиент|пользоват|юзер)", q.lower()):
        return None
    cnt = Customer.objects.filter(business=business).count()
    return QAResult(text=f"👥 Всего клиентов в базе: **{cnt}**.")

def _average_check(business, q, tz) -> Optional[QAResult]:
    if not re.search(r"средн[^\n]*(чек|покупк|заказ|сумм)", q.lower()):
        return None
    start, end, label = _period_bounds(q, tz)
    
    avg_amount = Redemption.objects.filter(
        coupon__campaign__business=business,
        redeemed_at__gte=start,
        redeemed_at__lte=end,
        amount__isnull=False
    ).aggregate(avg_amount=Avg('amount'))['avg_amount']
    
    if not avg_amount:
        return QAResult(text=f"💰 Нет данных о суммах чеков {label}.")
    
    return QAResult(text=f"💰 Средний чек {label}: **{avg_amount:.0f}** тг.")

def _wallet_adds(business, q, tz) -> Optional[QAResult]:
    if WalletPass is None:
        return None
    if not re.search(r"(сколько|ск)\s+.*(wallet|гугл|google).*(добав|сохран)", q.lower()):
        return None
    start, end, label = _period_bounds(q, tz)
    cnt = WalletPass.objects.filter(business=business, created_at__gte=start, created_at__lte=end).count()
    total = WalletPass.objects.filter(business=business).count()
    return QAResult(f"💳 Добавили карту в Wallet {label}: **{cnt}** (всего **{total}**).")

def _expiring_soon(business, q, tz) -> Optional[QAResult]:
    if not re.search(r"(истек|срок|expire)", q.lower()):
        return None
    m = re.search(r"в\s*ближайш\w*\s*(\d{1,2})\s*д", q.lower())
    days = int(m.group(1)) if m else 3
    tzinfo = pytz.timezone(tz)
    now = timezone.now().astimezone(tzinfo)
    end = now + timedelta(days=days)
    cnt = Coupon.objects.filter(campaign__business=business, expires_at__gt=now, expires_at__lte=end).count()
    return QAResult(f"⏳ Истекает в ближайшие {days} дн.: **{cnt}** купонов/карт.")

def _optouts(business, q, tz) -> Optional[QAResult]:
    if not re.search(r"(отписк|opt.?out)", q.lower()):
        return None
    # если есть журнал отписок; замените на свою модель
    try:
        from apps.contacts.models import OptOutEvent
    except Exception:
        return QAResult("🔕 Отписки: журнал не подключён.")
    start, end, label = _period_bounds(q, tz)
    by_channel = (OptOutEvent.objects
                  .filter(business=business, created_at__gte=start, created_at__lte=end)
                  .values('channel').annotate(n=Count('id')).order_by('-n'))
    txt = ", ".join([f"{r['channel']}: {r['n']}" for r in by_channel]) or "нет"
    return QAResult(f"🔕 Отписки {label}: {txt}.")

def _outbounds_yesterday(business, q, tz) -> Optional[QAResult]:
    if DeliveryAttempt is None:
        return None
    if not re.search(r"(сколько|ск)\s+.*(сообщен|отправлен).*вчера", q.lower()):
        return None
    tzinfo = pytz.timezone(tz)
    today = timezone.now().astimezone(tzinfo).date()
    d = today - timedelta(days=1)
    start = tzinfo.localize(datetime.combine(d, datetime.min.time()))
    end = tzinfo.localize(datetime.combine(d, datetime.max.time()))
    rows = (DeliveryAttempt.objects
            .filter(blast_recipient__blast__business=business, created_at__gte=start, created_at__lte=end)
            .values('channel').annotate(n=Count('id')).order_by('-n'))
    txt = ", ".join([f"{r['channel']}: {r['n']}" for r in rows]) or "0"
    return QAResult(f"📨 Отправлено сообщений вчера: {txt}.")

def _referrals_month(business, q, tz) -> Optional[QAResult]:
    if Referral is None:
        return None
    if not re.search(r"(реферал|друз|pay.?it.?forward)", q.lower()):
        return None
    tzinfo = pytz.timezone(tz)
    today = timezone.now().astimezone(tzinfo).date()
    start = tzinfo.localize(datetime.combine(today.replace(day=1), datetime.min.time()))
    ends = tzinfo.localize(datetime.combine(today, datetime.max.time()))
    total = Referral.objects.filter(business=business, created_at__gte=start, created_at__lte=ends).count()
    accepted = Referral.objects.filter(business=business, accepted=True,
                                       accepted_at__gte=start, accepted_at__lte=ends).count()
    return QAResult(f"🤝 Рефералки за месяц: создано **{total}**, активировано **{accepted}**.")

# Расширенные функции из предыдущей версии
def _top_campaign(business, q: str, tz: str) -> Optional[QAResult]:
    if not re.search(r"(лучш|топ|самая|популярн)[^\n]*(кампан|акци|промо)", q.lower()):
        return None
    
    start, end, period_label = _period_bounds(q, tz)
    
    top_campaign = Campaign.objects.filter(
        business=business,
        is_active=True
    ).annotate(
        redemptions_count=Count('coupons__redemption', filter=Q(coupons__redemption__redeemed_at__gte=start, coupons__redemption__redeemed_at__lte=end))
    ).order_by('-redemptions_count').first()
    
    if not top_campaign:
        return QAResult(text=f"📈 Нет данных о кампаниях {period_label}.")
    
    return QAResult(text=f"🏆 Лучшая кампания {period_label}: **{top_campaign.name}** ({top_campaign.redemptions_count} погашений).")

ANSWER_FUNCS = [
    _new_customers, _issues, _redeems, _cr_today, _active_campaigns,
    _total_customers, _average_check, _top_campaign,
    _wallet_adds, _expiring_soon, _optouts, _outbounds_yesterday, _referrals_month
]

def try_simple_qa(business, question: str, tzname: Optional[str] = None) -> Optional[QAResult]:
    tz = tzname or DEFAULT_TZ
    for fn in ANSWER_FUNCS:
        res = fn(business, question, tz)
        if res:
            return res
    return None
