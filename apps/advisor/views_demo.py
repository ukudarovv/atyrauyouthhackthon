from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from apps.businesses.models import Business

@csrf_exempt
def demo_login(request):
    """Demo login для тестирования AI Советчика"""
    if request.method == 'POST':
        username = request.POST.get('username', 'demo_user')
        password = request.POST.get('password', 'demo123')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            
            # Устанавливаем текущий бизнес в сессию
            business = Business.objects.filter(owner=user).first()
            if business:
                request.session['current_business_id'] = business.id
                messages.success(request, f'Вы вошли как {user.username}. Бизнес: {business.name}')
                return redirect('/advisor/chat/')
            else:
                messages.error(request, 'У пользователя нет бизнеса')
        else:
            messages.error(request, 'Неверные данные для входа')
    
    return render(request, 'demo_login.html')
