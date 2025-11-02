import re
from typing import Optional, Dict, Any, List

# Возвращаем список шагов {tool, args, note}
def match_intent(user_text: str) -> Optional[List[Dict[str, Any]]]:
    q = user_text.lower().strip()

    # Тренд за N дней
    m = re.search(r"тренд.*(выдач|погашен).*(\d+)\s*д", q)
    if m:
        metric = "issues" if "выдач" in m.group(0) else "redeems"
        days = int(m.group(2))
        return [
            {"tool":"analytics.query",
             "args":{"spec":{"metrics":[metric], "dimensions":["date"], "date_range":{"kind":f"last_{days}d"}}},
             "note": f"Тренд {metric} за {days}д"}
        ]

    # Топ кампаний по редемпам за 30 дней
    if re.search(r"топ.*кампан.*(редемп|погаш)", q):
        return [
            {"tool":"analytics.query",
             "args":{"spec":{"metrics":["redeems","cr_issue_redeem"],"dimensions":["campaign"],
                             "date_range":{"kind":"last_30d"},"order_by":[{"metric":"redeems","dir":"desc"}],"limit":10}},
             "note":"Топ кампаний 30д"}
        ]

    # Вклад каналов
    if re.search(r"(вклад|доля).*(канал|wa|sms|email|dm)", q):
        return [
            {"tool":"analytics.query",
             "args":{"spec":{"metrics":["issues","redeems"],"dimensions":["channel"],
                             "date_range":{"kind":"last_30d"},"order_by":[{"metric":"redeems","dir":"desc"}]}},
             "note":"Вклад каналов 30д"}
        ]

    # Сегменты — топ по размеру
    if re.search(r"топ.*сегмент", q):
        return [{"tool":"segments.top","args":{"limit":10},"note":"Топ сегментов"}]

    # Прогноз на 7–14 дней
    if re.search(r"(прогноз|сколько ожид).*(7|14)\s*д", q):
        days = 14 if "14" in q else 7
        return [{"tool":"forecast.redeems","args":{"days":days},"note":f"Прогноз на {days}д"}]

    # Оптимизировать каскад под бюджет
    m = re.search(r"оптимиз(ируй|ация).*(каскад).*(\d{3,})\s*([кк]?)", q)
    if m:
        budget = int(m.group(3))
        return [{"tool":"blast.optimize_cascade","args":{"budget":budget},"note":"Оптимизация каскада"}]

    # Черновик рассылки VIP на завтра 10:00 (простой парсер)
    if re.search(r"(сделай|создай).*рассылк", q) and "vip" in q:
        return [{
            "tool":"draft.blast",
            "args":{
                "name":"VIP завтра 10:00",
                "segment_id": 0,  # подставьте ID VIP в контроллере, если знаете
                "strategy": {"quiet_hours":{"start":"21:00","end":"09:00","timezone":"Asia/Almaty"}},
                "template": {"wa":{"text":"VIP −15% до 18:00. Покажите карту при оплате."}}
            },
            "note":"Черновик рассылки VIP"
        }]

    # Создать Wallet-оффер
    if re.search(r"созда.*wallet.*оффер", q):
        return [{
            "tool":"wallet.create_offer",
            "args":{
                "title":"Специальное предложение",
                "discount":"15%",
                "expires_in_days": 1
            },
            "note":"Создание Wallet-оффера"
        }]

    # Анализ недельного тренда
    if re.search(r"недельн.*тренд", q):
        return [
            {"tool":"analytics.query",
             "args":{"spec":{"metrics":["redeems","issues"], "dimensions":["date"], "date_range":{"kind":"last_14d"}}},
             "note": "Недельный тренд за 14 дней"}
        ]

    # Анализ по дням недели
    if re.search(r"дн(и|я|ям)\s+недел", q):
        return [
            {"tool":"analytics.query",
             "args":{"spec":{"metrics":["redeems","issues"], "dimensions":["weekday"], "date_range":{"kind":"last_30d"}}},
             "note": "Анализ по дням недели"}
        ]

    # Если ничего — вернём None → включится LLM-план
    return None
