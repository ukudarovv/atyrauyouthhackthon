# apps/ai/providers.py
import os, json
from typing import Dict, Any

class BaseLLM:
    def generate_copy(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError
    def translate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError
    def analyze_review(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """expects: {'text': str, 'rating': int|None, 'locale': 'ru'|'kk'}"""
        raise NotImplementedError

class DummyLLM(BaseLLM):
    def generate_copy(self, payload):
        import time
        import random
        
        title = payload.get('campaign_name') or 'Акция'
        custom_prompt = payload.get('custom_prompt', '').strip()
        
        # Базовые варианты
        base_headlines = [
            f"{title}: скидка 20%",
            f"{title} - выгодное предложение",
            f"Специальная цена на {title.lower()}",
            f"Только сегодня: {title}",
            f"Лучшая цена на {title.lower()}"
        ]
        
        base_ctas = [
            "Забрать скидку",
            "Получить предложение", 
            "Воспользоваться",
            "Заказать сейчас",
            "Узнать подробнее"
        ]
        
        # Если есть кастомный промпт, модифицируем варианты
        if custom_prompt:
            if "юмор" in custom_prompt.lower() or "игрив" in custom_prompt.lower():
                base_headlines = [
                    f"Ого! {title} со скидкой!",
                    f"{title} - это же мечта!",
                    f"Не поверишь: {title} дешевле!",
                    f"Секрет: {title} по супер-цене",
                    f"Вау! {title} почти даром!"
                ]
                base_ctas = ["Хочу!", "Давай!", "Забираю", "Го!", "Клёво!"]
            
            elif "премиум" in custom_prompt.lower() or "качеств" in custom_prompt.lower():
                base_headlines = [
                    f"Премиальный {title}",
                    f"Эксклюзивное предложение: {title}",
                    f"Высочайшее качество: {title}",
                    f"Роскошный {title} для вас",
                    f"Элитный {title} по специальной цене"
                ]
                base_ctas = ["Приобрести", "Заказать", "Выбрать", "Получить", "Оформить"]
            
            elif "эконом" in custom_prompt.lower() or "выгод" in custom_prompt.lower():
                base_headlines = [
                    f"Экономьте на {title}!",
                    f"Выгодный {title} для семьи",
                    f"Бюджетное решение: {title}",
                    f"Сэкономьте с {title}",
                    f"Доступный {title} высокого качества"
                ]
                base_ctas = ["Сэкономить", "Выгодно купить", "Сберечь деньги", "Купить дешевле", "Экономить"]
        
        # Добавляем случайность
        random.shuffle(base_headlines)
        random.shuffle(base_ctas)
        
        # Генерируем описание в зависимости от промпта
        if custom_prompt:
            if "юмор" in custom_prompt.lower() or "игрив" in custom_prompt.lower():
                description = f"Готов к веселью? {title} теперь еще круче! Мы решили сделать твой день ярче и добавили немного безумия в наше предложение. Не упусти шанс стать частью этой веселой истории!"
            elif "премиум" in custom_prompt.lower() or "качеств" in custom_prompt.lower():
                description = f"Откройте для себя мир {title.lower()} премиум-класса. Каждая деталь продумана до мелочей, чтобы обеспечить вам непревзойденное качество и исключительный опыт."
            elif "эконом" in custom_prompt.lower() or "выгод" in custom_prompt.lower():
                description = f"Умная экономия начинается с {title.lower()}! Мы знаем, как важно тратить деньги с умом, поэтому предлагаем вам максимальную выгоду без компромиссов в качестве."
            else:
                description = f"Откройте для себя новые возможности с {title.lower()}. Специальное предложение, созданное специально для вас."
        else:
            description = f"Воспользуйтесь уникальной возможностью получить {title.lower()} на выгодных условиях. Ограниченное время действия акции."
        
        return {
            "headline_variants": base_headlines,
            "cta_variants": base_ctas,
            "description": description,
            "seo": {
                "title": f"{title} — лучшее предложение рядом с вами", 
                "desc": f"Специальное предложение на {title.lower()}. Ограниченное время. Высокое качество и доступные цены."
            }
        }
        
    def translate(self, payload):
        return {"translated": f"[{payload.get('target_locale','kk')}] {payload.get('text','')}"}
    
    def analyze_review(self, payload):
        txt = (payload.get('text') or '').lower()
        rating = payload.get('rating', 3)
        
        # Простая логика для демо
        sentiment = 0
        if rating >= 4:
            sentiment = 60
        elif rating <= 2:
            sentiment = -60
        
        # Дополнительные модификаторы по тексту
        if any(word in txt for word in ["отлично", "супер", "вкусно", "быстро", "класс"]):
            sentiment += 20
        if any(word in txt for word in ["плохо", "ужасно", "медленно", "невкусно", "отвратительно"]):
            sentiment -= 40
            
        sentiment = max(-100, min(100, sentiment))
        
        # Определяем темы
        labels = []
        if any(word in txt for word in ["официант", "персонал", "обслуживание"]):
            labels.append("сервис")
        if any(word in txt for word in ["вкус", "еда", "блюдо", "готовят"]):
            labels.append("вкус")
        if any(word in txt for word in ["цена", "дорого", "дешево", "стоимость"]):
            labels.append("цена")
        if any(word in txt for word in ["быстро", "медленно", "ждать", "время"]):
            labels.append("скорость")
        if any(word in txt for word in ["чисто", "грязно", "уборка"]):
            labels.append("чистота")
        if any(word in txt for word in ["атмосфера", "интерьер", "музыка"]):
            labels.append("атмосфера")
        if any(word in txt for word in ["порция", "размер", "количество"]):
            labels.append("порции")
        if any(word in txt for word in ["меню", "выбор", "ассортимент"]):
            labels.append("меню")
        if any(word in txt for word in ["доставка", "курьер", "привезли"]):
            labels.append("доставка")
        
        # Проверка на токсичность
        toxic_words = ["дурак", "идиот", "убого", "отстой", "г*вно", "х*йня", "п*здец"]
        toxic = any(word in txt for word in toxic_words)
        
        # Генерируем краткое резюме
        if sentiment > 40:
            summary = f"Положительный отзыв ({rating}★). Клиент доволен."
        elif sentiment < -40:
            summary = f"Негативный отзыв ({rating}★). Есть проблемы."
        else:
            summary = f"Нейтральный отзыв ({rating}★). Смешанные впечатления."
            
        if labels:
            summary += f" Темы: {', '.join(labels[:3])}."
            
        return {
            "sentiment": sentiment,
            "labels": labels,
            "toxic": toxic,
            "summary": summary[:280]
        }

class AnthropicLLM(BaseLLM):
    """
    Интеграция с Anthropic Messages API.
    """
    def __init__(self, api_key: str, model: str):
        from anthropic import Anthropic  # официальный SDK
        self.client = Anthropic(api_key=api_key)
        self.model = model

    def _call(self, system: str, user: str, max_tokens: int = 1024) -> str:
        """
        Возвращаем plain text из контент-блоков ответа.
        """
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            temperature=0.7,
        )
        # В Messages API текст лежит в блоках content[]. Берем все text-блоки подряд.
        parts = []
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                parts.append(block.text)
        return "".join(parts)

    def _parse_json(self, raw: str) -> Dict[str, Any]:
        # Пытаемся достать чистый JSON (без ```), на случай если модель всё-таки добавит обёртку.
        try:
            return json.loads(raw)
        except Exception:
            start = raw.find("{"); end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(raw[start:end+1])
            raise

    def generate_copy(self, payload):
        import time
        import random
        
        # Добавляем уникальность для избежания кеширования
        timestamp = int(time.time())
        random_seed = random.randint(1000, 9999)
        
        system = (
            "Ты креативный маркетинговый копирайтер. Создавай разнообразные, уникальные тексты. "
            "Каждый раз генерируй НОВЫЕ варианты, не повторяй предыдущие. "
            "Отвечай СТРОГО в формате JSON без markdown и комментариев."
        )
        
        custom_prompt = payload.get('custom_prompt', '').strip()
        campaign_name = payload.get('campaign_name', 'Акция')
        description = payload.get('description', '')
        audience = payload.get('audience', 'локальные жители')
        
        if custom_prompt:
            # Кастомный промпт - делаем его основным фокусом
            user = (
                f"ВАЖНО: Следуй этому стилю и требованию: {custom_prompt}\n\n"
                f"Создай уникальные тексты для кампании:\n"
                f"• Название: {campaign_name}\n"
                f"• Описание: {description}\n"
                f"• Аудитория: {audience}\n"
                f"• Временная метка: {timestamp}-{random_seed}\n\n"
                f"Применяй стиль '{custom_prompt}' ко ВСЕМ текстам.\n"
                "Создай 5 РАЗНЫХ заголовков, 5 РАЗНЫХ призывов к действию, и описание.\n"
                "Длина: заголовки ≤ 60 символов, CTA ≤ 28 символов, описание ≤ 300 символов, SEO title ≤ 60, SEO desc ≤ 150.\n\n"
                "JSON схема:\n"
                "{\n"
                '  "headline_variants": ["вариант 1", "вариант 2", "вариант 3", "вариант 4", "вариант 5"],\n'
                '  "cta_variants": ["CTA 1", "CTA 2", "CTA 3", "CTA 4", "CTA 5"],\n'
                '  "description": "Подробное описание акции или предложения",\n'
                '  "seo": {"title": "SEO заголовок", "desc": "SEO описание"}\n'
                "}\n"
                "Только JSON, без комментариев!"
            )
        else:
            # Стандартный промпт с вариативностью
            user = (
                f"Создай разнообразные маркетинговые тексты для кампании:\n"
                f"• Название: {campaign_name}\n"
                f"• Описание: {description}\n"
                f"• Аудитория: {audience}\n"
                f"• ID генерации: {timestamp}-{random_seed}\n\n"
                "Создай 5 УНИКАЛЬНЫХ заголовков в разных стилях:\n"
                "1. Эмоциональный\n"
                "2. Рациональный (цифры/факты)\n"
                "3. Срочность/ограниченность\n"
                "4. Выгода/экономия\n"
                "5. Интригующий/вопрос\n\n"
                "5 РАЗНЫХ призывов к действию:\n"
                "1. Прямой\n"
                "2. Мягкий\n"
                "3. Игривый\n"
                "4. Срочный\n"
                "5. Вовлекающий\n\n"
                "Длина: заголовки ≤ 60 символов, CTA ≤ 28 символов, описание ≤ 300 символов.\n\n"
                "JSON схема:\n"
                "{\n"
                '  "headline_variants": ["заголовок 1", "заголовок 2", "заголовок 3", "заголовок 4", "заголовок 5"],\n'
                '  "cta_variants": ["CTA 1", "CTA 2", "CTA 3", "CTA 4", "CTA 5"],\n'
                '  "description": "Подробное описание предложения или акции",\n'
                '  "seo": {"title": "SEO заголовок ≤60", "desc": "SEO описание ≤150"}\n'
                "}\n"
                "Только валидный JSON!"
            )
        
        raw = self._call(system, user, max_tokens=1200)
        return self._parse_json(raw)

    def translate(self, payload):
        system = (
            "Ты переводчик маркетинговых текстов. Сохраняй смысл и цифры/проценты. "
            "Отвечай СТРОГО как чистый текст, без markdown/префиксов/комментариев."
        )
        user = f"Переведи на {payload.get('target_locale','kk')}:\n\n{payload.get('text','')}"
        out = self._call(system, user, max_tokens=800)
        return {"translated": out.strip()}
    
    def analyze_review(self, payload):
        system = (
            "Ты модератор отзывов ресторана. "
            "Анализируй тональность, темы и токсичность. "
            "Верни СТРОГО JSON: {\"sentiment\": int -100..100, "
            "\"labels\": [строки], \"toxic\": bool, \"summary\": строка<=200}. "
            "Язык входа русский/казахский; в labels используй короткие рубрики: "
            "['сервис','вкус','цена','скорость','чистота','атмосфера','персонал','порции','меню','доставка']. "
            "Sentiment: -100 очень негативно, 0 нейтрально, +100 очень позитивно. "
            "Toxic: true если есть мат, оскорбления, угрозы, неприемлемый контент."
        )
        
        text = payload.get("text", "")[:4000]  # Ограничиваем длину
        rating = payload.get("rating")
        locale = payload.get("locale", "ru")
        
        user = (
            f"Отзыв ресторана на языке {locale}:\n"
            f"Оценка: {rating if rating is not None else 'не указана'} звёзд\n"
            f"Текст: {text}\n\n"
            "Проанализируй и ответь строго валидным JSON без пояснений."
        )
        
        raw = self._call(system, user, max_tokens=600)
        return self._parse_json(raw)

def get_llm():
    provider = os.getenv('AI_PROVIDER', 'anthropic').lower()
    if provider == 'anthropic' and os.getenv('ANTHROPIC_API_KEY'):
        return AnthropicLLM(os.getenv('ANTHROPIC_API_KEY'), os.getenv('AI_MODEL_NAME','claude-3-5-sonnet-latest'))
    return DummyLLM()
