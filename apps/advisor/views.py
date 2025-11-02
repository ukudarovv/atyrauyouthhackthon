from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from apps.businesses.models import Business
from .models import AdvisorSession, AdvisorMessage
from .qa_simple_extended import try_simple_qa, DEFAULT_TZ
from .engine import make_plan, execute_plan
from .smart_suggestions import get_smart_suggestions, get_contextual_tips
from .export_system import ExportSystem, export_chat_history
from .ai_insights import AIInsightsEngine, get_business_health_score
import json

def get_current_business(request):
    """Получить текущий бизнес пользователя"""
    if not request.user.is_authenticated:
        return None
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        return None
    return Business.objects.filter(id=biz_id, owner=request.user).first()

@login_required
def chat(request):
    """Главная страница чата с AI советчиком"""
    business = get_current_business(request)
    if not business:
        # Попробуем автоматически выбрать первый бизнес пользователя
        first_business = Business.objects.filter(owner=request.user).first()
        if first_business:
            request.session['current_business_id'] = first_business.id
            business = first_business
        else:
            return render(request, 'advisor/no_business.html')
    
    # Получаем или создаем активную сессию
    session, created = AdvisorSession.objects.get_or_create(
        user=request.user,
        business=business,
        is_active=True,
        defaults={'business': business}
    )
    
    messages = session.messages.order_by('created_at')
    
    # Получаем умные предложения
    smart_suggestions = get_smart_suggestions(session)
    contextual_tips = get_contextual_tips(business)
    
    # AI инсайты
    insights_engine = AIInsightsEngine(business)
    ai_insights = insights_engine.generate_insights()[:3]  # Топ 3
    daily_digest = insights_engine.get_daily_digest()
    health_score = get_business_health_score(business)
    
    context = {
        'session': session,
        'messages': messages,
        'business': business,
        'smart_suggestions': smart_suggestions,
        'contextual_tips': contextual_tips,
        'ai_insights': ai_insights,
        'daily_digest': daily_digest,
        'health_score': health_score,
    }
    
    if request.method == 'POST':
        return _handle_chat_message(request, session)
    
    return render(request, 'advisor/chat.html', context)

def _handle_chat_message(request, session):
    """Обработка сообщения в чате"""
    text = (request.POST.get('q') or '').strip()
    
    if not text:
        return HttpResponseBadRequest("Пустое сообщение")

    # Сохраняем сообщение пользователя
    user_message = AdvisorMessage.objects.create(
        session=session,
        role='user',
        content={"text": text}
    )

    # 🔹 Быстрые вопросы — отвечаем сразу, без LLM
    tzname = getattr(getattr(session.business, 'timezone', None), 'key', None) or DEFAULT_TZ
    quick = try_simple_qa(session.business, text, tzname=tzname)
    
    if quick:
        assistant_message = AdvisorMessage.objects.create(
            session=session,
            role='assistant',
            content={"text": quick.text, "mode": "quick"}
        )
        return render(request, 'advisor/_messages.html', {
            "messages": session.messages.order_by('created_at')
        })

    # Если быстрый ответ не найден, пробуем детерминированные интенты
    brief = {"business": session.business.name, "active_campaigns": 3}  # Заглушка для brief
    plan = make_plan(text, brief)
    
    if plan.intention == "rule_based":
        # Выполняем план без LLM
        result = execute_plan(plan, session.business)
        assistant_message = AdvisorMessage.objects.create(
            session=session,
            role='assistant',
            content={"text": result, "mode": "rule_based"}
        )
    else:
        # LLM fallback или заглушка
        result = execute_plan(plan, session.business)
        assistant_message = AdvisorMessage.objects.create(
            session=session,
            role='assistant',
            content={"text": result, "mode": "analytics"}
        )
    
    return render(request, 'advisor/_messages.html', {
        "messages": session.messages.order_by('created_at')
    })

@login_required
def export_analytics(request, format):
    """Экспорт аналитических данных"""
    business = get_current_business(request)
    if not business:
        return HttpResponseBadRequest("Бизнес не найден")
    
    export_system = ExportSystem(business)
    
    # Данные для экспорта (можно расширить)
    export_data = {
        'period_days': 30,
        'include_campaigns': True,
        'include_daily_stats': True
    }
    
    if format in ['excel', 'pdf', 'csv']:
        return export_system.export_analytics_excel(export_data, format)
    else:
        return HttpResponseBadRequest("Неподдерживаемый формат")

@login_required
def export_chat(request, session_id, format):
    """Экспорт истории чата"""
    try:
        session = AdvisorSession.objects.get(
            id=session_id,
            user=request.user
        )
        return export_chat_history(session, format)
    except AdvisorSession.DoesNotExist:
        return HttpResponseBadRequest("Сессия не найдена")

@login_required
@require_http_methods(["POST"])
def new_session(request):
    """Создать новую сессию чата"""
    from django.shortcuts import redirect
    
    business = get_current_business(request)
    if not business:
        return HttpResponseBadRequest("Бизнес не выбран")
    
    # Деактивируем старые сессии
    AdvisorSession.objects.filter(
        user=request.user,
        business=business,
        is_active=True
    ).update(is_active=False)
    
    # Создаем новую сессию
    session = AdvisorSession.objects.create(
        user=request.user,
        business=business
    )
    
    # Перенаправляем обратно на чат
    return redirect('advisor:chat')
