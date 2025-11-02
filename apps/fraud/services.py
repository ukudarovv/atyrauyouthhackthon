from django.utils import timezone
from django.db.models import Count
from datetime import timedelta
from typing import Tuple, Dict, Any, List

from apps.fraud.models import RiskEvent, RiskKind, RiskDecision
from apps.coupons.models import Coupon
from apps.campaigns.models import TrackEvent, TrackEventType

def _get_fraud_settings(business) -> dict:
    """Получает настройки антифрода для бизнеса"""
    default = {
        "issue_ip_per_hour": 20,
        "phone_per_day": 2,
        "burst_distinct_phones_ip_10m": 5,
        "night_hours": [0, 6],
        "utm_deny": [],
        "ip_deny": [],
        "phone_deny": [],
        "ip_allow": [],
        "action_thresholds": {"warn": 20, "block": 50},
    }
    cfg = (business.settings or {}).get("fraud", {})
    merged = {**default, **cfg}
    # нормализация
    merged["action_thresholds"].setdefault("warn", 20)
    merged["action_thresholds"].setdefault("block", 50)
    return merged

def _client_meta(request) -> dict:
    """Извлекает метаданные клиента из запроса"""
    return {
        "ip": request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR'),
        "ua": request.META.get('HTTP_USER_AGENT', ''),
        "utm": _parse_utm(request),
    }

def _parse_utm(request) -> dict:
    """Парсит UTM параметры из запроса"""
    q = request.GET or request.POST
    keys = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"]
    return {k: q.get(k) for k in keys if q.get(k)}

def _in_night(now, night_hours: List[int]) -> bool:
    """Проверяет, попадает ли время в ночные часы"""
    if not night_hours or len(night_hours) < 2:
        return False
    start, end = night_hours[0], night_hours[1]
    h = now.hour
    if start <= end:
        return start <= h < end
    # если [22, 6] - ночь через полночь
    return h >= start or h < end

def score_issue(request, *, campaign, phone: str) -> Tuple[int, List[str], str]:
    """
    Оценивает риск при выдаче купона
    Возвращает (score, reasons, decision)
    decision: 'allow'|'warn'|'block'
    """
    biz = campaign.business
    now = timezone.now()
    meta = _client_meta(request)
    ip = meta["ip"]
    ua = meta["ua"]
    utm = meta["utm"]

    cfg = _get_fraud_settings(biz)
    score = 0
    reasons = []

    # allowlist (касса/офис)
    if ip and ip in cfg.get("ip_allow", []):
        RiskEvent.objects.create(
            business=biz, kind=RiskKind.ISSUE, campaign_id=campaign.id,
            phone=phone, ip=ip, ua=ua, utm=utm, 
            score=0, reasons=["ip_allow:0"], decision=RiskDecision.ALLOW
        )
        return 0, ["ip_allow:0"], RiskDecision.ALLOW

    # 1) жёсткие deny
    if ip and ip in cfg.get("ip_deny", []):
        score += 100
        reasons.append("ip_deny:+100")
    if phone and phone in cfg.get("phone_deny", []):
        score += 100
        reasons.append("phone_deny:+100")
    for v in (utm or {}).values():
        if any(bad.lower() in v.lower() for bad in cfg.get("utm_deny", [])):
            score += 50
            reasons.append("utm_deny:+50")
            break

    # 2) частота выдач с IP за 1 час
    if ip:
        hour_ago = now - timedelta(hours=1)
        ip_issues_1h = Coupon.objects.filter(
            campaign__business=biz,
            issued_at__gte=hour_ago,
            metadata__ip=ip
        ).count()
        
        if ip_issues_1h > cfg["issue_ip_per_hour"]:
            delta = ip_issues_1h - cfg["issue_ip_per_hour"]
            add = 10 + min(40, delta * 2)
            score += add
            reasons.append(f"ip_many_1h:+{add} ({ip_issues_1h})")

    # 3) выдачи на телефон за 24ч
    if phone:
        day_ago = now - timedelta(hours=24)
        phone_issues_24h = Coupon.objects.filter(
            campaign__business=biz, 
            phone=phone, 
            issued_at__gte=day_ago
        ).count()
        
        if phone_issues_24h >= cfg["phone_per_day"]:
            add = 20 + (phone_issues_24h - cfg["phone_per_day"]) * 10
            score += add
            reasons.append(f"phone_many_24h:+{add} ({phone_issues_24h})")

    # 4) бурст разных телефонов с одного IP за 10 мин
    if ip:
        ten_min_ago = now - timedelta(minutes=10)
        burst = Coupon.objects.filter(
            campaign__business=biz, 
            issued_at__gte=ten_min_ago,
            metadata__ip=ip
        ).values('phone').distinct().count()
        
        if burst >= cfg["burst_distinct_phones_ip_10m"]:
            add = 15 + (burst - cfg["burst_distinct_phones_ip_10m"]) * 5
            score += add
            reasons.append(f"ip_burst_10m:+{add} ({burst})")

    # 5) ночные часы
    if _in_night(now, cfg["night_hours"]):
        score += 10
        reasons.append("night:+10")

    # Итоговое решение
    warn_th = cfg["action_thresholds"]["warn"]
    block_th = cfg["action_thresholds"]["block"]
    decision = RiskDecision.ALLOW
    if score >= block_th:
        decision = RiskDecision.BLOCK
    elif score >= warn_th:
        decision = RiskDecision.WARN

    # Запишем RiskEvent
    RiskEvent.objects.create(
        business=biz, kind=RiskKind.ISSUE, campaign_id=campaign.id,
        phone=phone, ip=ip, ua=ua, utm=utm, 
        score=score, reasons=reasons, decision=decision
    )
    
    return score, reasons, decision

def score_redeem(request, *, coupon) -> Tuple[int, List[str], str]:
    """
    Оценивает риск при погашении купона
    Упрощённо: проверим ip_deny/allow и повторные редемпшены с одного IP.
    """
    biz = coupon.campaign.business
    now = timezone.now()
    meta = _client_meta(request)
    ip = meta["ip"]
    ua = meta["ua"]
    utm = meta["utm"]
    cfg = _get_fraud_settings(biz)

    # allowlist
    if ip and ip in cfg.get("ip_allow", []):
        RiskEvent.objects.create(
            business=biz, kind=RiskKind.REDEEM, campaign_id=coupon.campaign_id,
            coupon=coupon, ip=ip, ua=ua, utm=utm, 
            score=0, reasons=["ip_allow:0"], decision=RiskDecision.ALLOW
        )
        return 0, ["ip_allow:0"], RiskDecision.ALLOW

    score = 0
    reasons = []

    # deny IP
    if ip and ip in cfg.get("ip_deny", []):
        score += 80
        reasons.append("ip_deny:+80")

    # попытки редемпшена по разным купонам с одного IP за 10 мин
    if ip:
        ten_min_ago = now - timedelta(minutes=10)
        ip_redeems_10m = RiskEvent.objects.filter(
            business=biz, 
            kind=RiskKind.REDEEM, 
            created_at__gte=ten_min_ago, 
            ip=ip
        ).count()
        
        if ip_redeems_10m >= 10:
            add = 30
            score += add
            reasons.append(f"redeem_burst_ip_10m:+{add} ({ip_redeems_10m})")

    # ночные часы
    if _in_night(now, cfg["night_hours"]):
        score += 10
        reasons.append("night:+10")

    # решение
    warn_th = cfg["action_thresholds"]["warn"]
    block_th = cfg["action_thresholds"]["block"]
    decision = RiskDecision.ALLOW
    if score >= block_th:
        decision = RiskDecision.BLOCK
    elif score >= warn_th:
        decision = RiskDecision.WARN

    # записываем событие
    RiskEvent.objects.create(
        business=biz, kind=RiskKind.REDEEM, campaign_id=coupon.campaign_id,
        coupon=coupon, ip=ip, ua=ua, utm=utm, 
        score=score, reasons=reasons, decision=decision
    )
    
    return score, reasons, decision
