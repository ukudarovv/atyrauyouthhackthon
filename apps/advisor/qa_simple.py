import re
from dataclasses import dataclass
from typing import Optional, Tuple
from django.utils import timezone
from datetime import timedelta, datetime
import pytz
from django.db.models import Count
from apps.customers.models import Customer
from apps.coupons.models import Coupon
from apps.redemptions.models import Redemption

# Базовая TZ: можно заменить на business.timezone, если есть поле
DEFAULT_TZ = "Asia/Atyrau"

@dataclass
class QAResult:
    text: str

# ---------- Разбор периодов на RU ----------
def _period_bounds(q: str, tzname: str) -> Tuple[datetime, datetime, str]:
    tz = pytz.timezone(tzname)
    now = timezone.now().astimezone(tz)
    today = now.date()

    q_norm = q.lower().strip()

    # сегодня
    if any(w in q_norm for w in ["сегодня", "today"]):
        start = tz.localize(datetime.combine(today, datetime.min.time()))
        end   = tz.localize(datetime.combine(today, datetime.max.time()))
        return start, end, "сегодня"

    # вчера
    if any(w in q_norm for w in ["вчера", "yesterday"]):
        d = today - timedelta(days=1)
        start = tz.localize(datetime.combine(d, datetime.min.time()))
        end   = tz.localize(datetime.combine(d, datetime.max.time()))
        return start, end, "вчера"

    # за неделю / последнюю неделю / на этой неделе
    if re.search(r"(за|последн)[^\n]*недел", q_norm) or "эта неделя" in q_norm or "на этой неделе" in q_norm:
        # неделя с понедельника по сегодня
        weekday = today.weekday()  # 0=Mon
        start_d = today - timedelta(days=weekday)
        start = tz.localize(datetime.combine(start_d, datetime.min.time()))
        end   = tz.localize(datetime.combine(today, datetime.max.time()))
        return start, end, "эта неделя"

    # за месяц / последний месяц / в этом месяце
    if re.search(r"(за|последн)[^\n]*месяц", q_norm) or "этот месяц" in q_norm or "в этом месяце" in q_norm:
        start_d = today.replace(day=1)
        start = tz.localize(datetime.combine(start_d, datetime.min.time()))
        end   = tz.localize(datetime.combine(today, datetime.max.time()))
        return start, end, "этот месяц"

    # по умолчанию — сегодня
    start = tz.localize(datetime.combine(today, datetime.min.time()))
    end   = tz.localize(datetime.combine(today, datetime.max.time()))
    return start, end, "сегодня"

# ---------- Ответчики ----------
def _answer_new_customers(business, q: str, tz: str) -> Optional[QAResult]:
    if not re.search(r"(сколько|ск|количество)\s+.*(новых|новы[йе]|регистрац|пришл)\s*(клиент|пользоват|юзер)", q.lower()):
        return None
    
    start, end, period_label = _period_bounds(q, tz)
    
    # считаем по first_seen (если пусто — по created_at)
    cnt = Customer.objects.filter(
        business=business,
        first_seen__gte=start, 
        first_seen__lte=end
    ).count()
    
    # fallback если first_seen не заполнялся
    if cnt == 0:
        cnt = Customer.objects.filter(business=business, created_at__gte=start, created_at__lte=end).count()
    
    return QAResult(text=f"🧾 Новых клиентов {period_label}: **{cnt}**.")

def _answer_issues(business, q: str, tz: str) -> Optional[QAResult]:
    if not re.search(r"(сколько|ск|количество)\s+.*(выдано|выдач|создано|сгенерир|купон[ао]в|скидок|промо|issues?)", q.lower()):
        return None
    start, end, period_label = _period_bounds(q, tz)
    cnt = Coupon.objects.filter(campaign__business=business, issued_at__gte=start, issued_at__lte=end).count()
    return QAResult(text=f"🎟️ Выдач купонов {period_label}: **{cnt}**.")

def _answer_redeems(business, q: str, tz: str) -> Optional[QAResult]:
    if not re.search(r"(сколько|ск|количество)\s+.*(погашен|использован|активир|редемп|redeem|применен)", q.lower()):
        return None
    start, end, period_label = _period_bounds(q, tz)
    cnt = Redemption.objects.filter(coupon__campaign__business=business, redeemed_at__gte=start, redeemed_at__lte=end).count()
    return QAResult(text=f"✅ Погашений {period_label}: **{cnt}**.")

def _answer_active_campaigns(business, q: str, tz: str) -> Optional[QAResult]:
    if not re.search(r"(сколько|ск|количество)\s+.*(активн|работа|запущен)[^\n]*(кампан|акци|промо)", q.lower()):
        return None
    from apps.campaigns.models import Campaign
    start, end, _ = _period_bounds(q, tz)
    cnt = Campaign.objects.filter(business=business, is_active=True).count()
    return QAResult(text=f"📣 Активных кампаний сейчас: **{cnt}**.")

# Дополнительные быстрые ответы
def _answer_total_customers(business, q: str, tz: str) -> Optional[QAResult]:
    if not re.search(r"(сколько|ск|количество)\s+.*(всего|общ|итого|всех)[^\n]*(клиент|пользоват|юзер)", q.lower()):
        return None
    cnt = Customer.objects.filter(business=business).count()
    return QAResult(text=f"👥 Всего клиентов в базе: **{cnt}**.")

def _answer_conversion_rate(business, q: str, tz: str) -> Optional[QAResult]:
    if not re.search(r"(cr|конверс|коэффициент|процент|доля).*(погашен|использован|активир)", q.lower()):
        return None
    start, end, period_label = _period_bounds(q, tz)
    
    issues = Coupon.objects.filter(campaign__business=business, issued_at__gte=start, issued_at__lte=end).count()
    redeems = Redemption.objects.filter(coupon__campaign__business=business, redeemed_at__gte=start, redeemed_at__lte=end).count()
    
    if issues == 0:
        return QAResult(text=f"📊 CR {period_label}: нет выдач купонов.")
    
    cr = round(redeems / issues * 100, 1)
    return QAResult(text=f"📊 CR {period_label}: **{cr}%** ({redeems} из {issues}).")

# Маркетинговые и аналитические вопросы
def _answer_top_campaign(business, q: str, tz: str) -> Optional[QAResult]:
    if not re.search(r"(лучш|топ|самая|популярн)[^\n]*(кампан|акци|промо)", q.lower()):
        return None
    
    from apps.campaigns.models import Campaign
    from django.db.models import Count
    
    start, end, period_label = _period_bounds(q, tz)
    
    top_campaign = Campaign.objects.filter(
        business=business,
        is_active=True
    ).annotate(
        redemptions_count=Count('coupons__redemption')
    ).order_by('-redemptions_count').first()
    
    if not top_campaign:
        return QAResult(text=f"📈 Нет данных о кампаниях {period_label}.")
    
    return QAResult(text=f"🏆 Лучшая кампания: **{top_campaign.name}** ({top_campaign.redemptions_count} погашений).")

def _answer_weekly_trend(business, q: str, tz: str) -> Optional[QAResult]:
    if not re.search(r"(тренд|динамик|рост|падени)[^\n]*(недел|week)", q.lower()):
        return None
    
    from django.utils import timezone
    from datetime import timedelta
    
    tz_obj = pytz.timezone(tz)
    now = timezone.now().astimezone(tz_obj)
    
    # Эта неделя
    current_week_start = now.date() - timedelta(days=now.weekday())
    current_week_end = now.date()
    
    # Прошлая неделя
    prev_week_start = current_week_start - timedelta(days=7)
    prev_week_end = current_week_start - timedelta(days=1)
    
    current_week_redeems = Redemption.objects.filter(
        coupon__campaign__business=business,
        redeemed_at__date__gte=current_week_start,
        redeemed_at__date__lte=current_week_end
    ).count()
    
    prev_week_redeems = Redemption.objects.filter(
        coupon__campaign__business=business,
        redeemed_at__date__gte=prev_week_start,
        redeemed_at__date__lte=prev_week_end
    ).count()
    
    if prev_week_redeems == 0:
        return QAResult(text=f"📈 Недельный тренд: эта неделя **{current_week_redeems}** погашений (нет данных за прошлую неделю).")
    
    change = ((current_week_redeems - prev_week_redeems) / prev_week_redeems) * 100
    trend_icon = "📈" if change > 0 else "📉" if change < 0 else "➡️"
    
    return QAResult(text=f"{trend_icon} Недельный тренд: **{change:+.1f}%** ({current_week_redeems} vs {prev_week_redeems}).")

def _answer_customer_retention(business, q: str, tz: str) -> Optional[QAResult]:
    if not re.search(r"(возвращ|retention|удержан|повторн)[^\n]*(клиент|пользоват)", q.lower()):
        return None
    
    from django.db.models import Count
    
    # Клиенты с более чем одним погашением
    repeat_customers = Customer.objects.filter(
        business=business
    ).annotate(
        redemption_count=Count('phone_e164__in', 
            queryset=Redemption.objects.filter(coupon__campaign__business=business).values_list('coupon__phone', flat=True))
    ).filter(redemption_count__gt=1).count()
    
    total_customers = Customer.objects.filter(business=business).count()
    
    if total_customers == 0:
        return QAResult(text=f"🔄 Нет данных о клиентах.")
    
    retention_rate = round((repeat_customers / total_customers) * 100, 1)
    return QAResult(text=f"🔄 Retention rate: **{retention_rate}%** ({repeat_customers} из {total_customers} возвращаются).")

def _answer_average_order_value(business, q: str, tz: str) -> Optional[QAResult]:
    if not re.search(r"средн[^\n]*(чек|покупк|заказ|сумм)", q.lower()):
        return None
    
    from django.db.models import Avg
    
    start, end, period_label = _period_bounds(q, tz)
    
    avg_amount = Redemption.objects.filter(
        coupon__campaign__business=business,
        redeemed_at__gte=start,
        redeemed_at__lte=end,
        amount__isnull=False
    ).aggregate(avg_amount=Avg('amount'))['avg_amount']
    
    if not avg_amount:
        return QAResult(text=f"💰 Нет данных о суммах чеков {period_label}.")
    
    return QAResult(text=f"💰 Средний чек {period_label}: **{avg_amount:.0f}** тг.")

def _answer_peak_hours(business, q: str, tz: str) -> Optional[QAResult]:
    if not re.search(r"(пик|час|время)[^\n]*(активн|популярн|больш)", q.lower()):
        return None
    
    from django.db.models import Count
    from django.db.models.functions import Extract
    
    start, end, period_label = _period_bounds(q, tz)
    
    peak_hour = Redemption.objects.filter(
        coupon__campaign__business=business,
        redeemed_at__gte=start,
        redeemed_at__lte=end
    ).annotate(
        hour=Extract('redeemed_at', 'hour')
    ).values('hour').annotate(
        count=Count('id')
    ).order_by('-count').first()
    
    if not peak_hour:
        return QAResult(text=f"⏰ Нет данных о времени активности {period_label}.")
    
    return QAResult(text=f"⏰ Пиковое время {period_label}: **{peak_hour['hour']:02d}:00** ({peak_hour['count']} погашений).")

def _answer_campaign_roi(business, q: str, tz: str) -> Optional[QAResult]:
    if not re.search(r"(roi|рентабельн|окупаем|эффективн)[^\n]*(кампан|акци)", q.lower()):
        return None
    
    from apps.campaigns.models import Campaign
    from django.db.models import Count, Sum
    
    start, end, period_label = _period_bounds(q, tz)
    
    campaigns_with_metrics = Campaign.objects.filter(
        business=business,
        is_active=True
    ).annotate(
        total_issued=Count('coupons', filter=models_Q(coupons__issued_at__gte=start, coupons__issued_at__lte=end)),
        total_redeemed=Count('coupons__redemption', filter=models_Q(coupons__redemption__redeemed_at__gte=start, coupons__redemption__redeemed_at__lte=end)),
        total_revenue=Sum('coupons__redemption__amount', filter=models_Q(coupons__redemption__redeemed_at__gte=start, coupons__redemption__redeemed_at__lte=end))
    ).filter(total_issued__gt=0)
    
    if not campaigns_with_metrics:
        return QAResult(text=f"📊 Нет данных о ROI кампаний {period_label}.")
    
    total_revenue = sum(c.total_revenue or 0 for c in campaigns_with_metrics)
    total_campaigns = campaigns_with_metrics.count()
    
    return QAResult(text=f"💎 ROI кампаний {period_label}: **{total_revenue:.0f}** тг выручки от {total_campaigns} кампаний.")

# Список простых «интентов»
ANSWER_FUNCS = [
    _answer_new_customers,
    _answer_issues,
    _answer_redeems,
    _answer_active_campaigns,
    _answer_total_customers,
    _answer_conversion_rate,
    # Маркетинговые и аналитические функции
    _answer_top_campaign,
    _answer_weekly_trend,
    _answer_customer_retention,
    _answer_average_order_value,
    _answer_peak_hours,
    _answer_campaign_roi,
]

def try_simple_qa(business, question: str, tzname: Optional[str] = None) -> Optional[QAResult]:
    tz = tzname or DEFAULT_TZ
    for fn in ANSWER_FUNCS:
        res = fn(business, question, tz)
        if res:
            return res
    return None
