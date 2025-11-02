from functools import wraps
from django.http import HttpResponseForbidden

def role_required(*roles):
    def deco(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            u = request.user
            if not u.is_authenticated or (not u.is_superuser and u.role not in roles):
                return HttpResponseForbidden('Недостаточно прав')
            return view(request, *args, **kwargs)
        return _wrapped
    return deco
