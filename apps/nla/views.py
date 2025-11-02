"""
Views для Natural Language Analytics
"""
import json
import csv
import io
import logging
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.utils import timezone
from django.core.exceptions import PermissionDenied

from apps.businesses.models import Business
from .providers import nl_to_spec
from .builder import run_spec

logger = logging.getLogger(__name__)

def _get_current_business(request):
    """
    Получает текущий бизнес пользователя
    """
    biz_id = request.session.get('current_business_id')
    if not biz_id:
        return None
    
    if request.user.is_superuser:
        return Business.objects.filter(id=biz_id).first()
    else:
        return Business.objects.filter(id=biz_id, owner=request.user).first()

@login_required
def ask(request):
    """
    Основная страница NL-аналитики
    """
    # Проверяем права доступа
    if not (request.user.is_superuser or request.user.role in ('manager', 'owner')):
        raise PermissionDenied('Недостаточно прав для доступа к аналитике')
    
    business = _get_current_business(request)
    context = {"need_business": not bool(business)}
    
    if request.method == "POST" and business:
        question = (request.POST.get('q') or '').strip()
        
        if not question:
            return HttpResponseBadRequest("Вопрос не может быть пустым")
        
        if len(question) > 500:
            return HttpResponseBadRequest("Вопрос слишком длинный (максимум 500 символов)")
        
        try:
            # Преобразуем вопрос в спецификацию
            spec = nl_to_spec(question)
            logger.info(f"Generated spec for question '{question}': {spec}")
            
            # Выполняем запрос
            rows, meta = run_spec(business, spec)
            logger.info(f"Query returned {len(rows)} rows")
            
            context.update({
                "question": question,
                "spec": spec,
                "rows": rows,
                "meta": meta,
                "spec_json": json.dumps(spec)
            })
            
            # Если это HTMX запрос, возвращаем только результат
            if request.headers.get('HX-Request'):
                return render(request, 'nla/_result.html', context)
            
        except Exception as e:
            logger.error(f"Error processing question '{question}': {e}")
            context["error"] = f"Ошибка обработки запроса: {str(e)}"
            
            if request.headers.get('HX-Request'):
                return render(request, 'nla/_error.html', context)
    
    return render(request, 'nla/ask.html', context)

@login_required
def ask_csv(request):
    """
    Экспорт результатов в CSV
    """
    # Проверяем права доступа
    if not (request.user.is_superuser or request.user.role in ('manager', 'owner')):
        raise PermissionDenied('Недостаточно прав для экспорта данных')
    
    business = _get_current_business(request)
    if not business:
        return HttpResponseBadRequest("Бизнес не выбран")
    
    # Получаем спецификацию из POST данных
    spec_raw = request.POST.get('spec')
    question = request.POST.get('question', 'Запрос')
    
    if not spec_raw:
        return HttpResponseBadRequest("Спецификация запроса не найдена")
    
    try:
        spec = json.loads(spec_raw)
        rows, meta = run_spec(business, spec)
        
        # Формируем CSV
        output = io.StringIO()
        
        if rows:
            headers = list(rows[0].keys())
        else:
            headers = (meta.get('dimensions') or []) + (meta.get('metrics') or [])
        
        writer = csv.writer(output)
        
        # Заголовок файла
        writer.writerow([f'# Экспорт аналитики: {question}'])
        writer.writerow([f'# Период: {meta.get("start")} - {meta.get("end")}'])
        writer.writerow([f'# Метрики: {", ".join(meta.get("metrics", []))}'])
        writer.writerow([f'# Измерения: {", ".join(meta.get("dimensions", []))}'])
        writer.writerow([])  # Пустая строка
        
        # Заголовки столбцов
        writer.writerow(headers)
        
        # Данные
        for row in rows:
            writer.writerow([row.get(header, "") for header in headers])
        
        # Подготавливаем HTTP ответ
        response = HttpResponse(
            output.getvalue(), 
            content_type='text/csv; charset=utf-8'
        )
        
        # Генерируем имя файла
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        filename = f'analytics_{timestamp}.csv'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        logger.info(f"CSV export: {len(rows)} rows exported for business {business.name}")
        
        return response
        
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Неверный формат спецификации")
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}")
        return HttpResponseBadRequest(f"Ошибка экспорта: {str(e)}")
