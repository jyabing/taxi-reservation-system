# common/views.py

from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from .models import LinkClickLog
from django.contrib.auth.decorators import login_required
from django.utils.timezone import now

@require_POST
@csrf_exempt  # 如果你使用 AJAX Fetch 且未加 CSRF Token，可保留；否则建议移除并在前端加 csrfmiddlewaretoken
def log_link_click(request):
    user = request.user if request.user.is_authenticated else None
    link_name = request.POST.get("name", "")
    link_url = request.POST.get("url", "")

    if not link_url:
        return JsonResponse({"status": "error", "message": "Missing URL"}, status=400)

    LinkClickLog.objects.create(
        user=user,
        link_name=link_name,
        link_url=link_url,
        timestamp=now(),
    )
    return JsonResponse({"status": "ok"})
