# ✅ 文件路径：common/middleware.py
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
from django.urls import resolve
from collections import defaultdict

class LinkClickTrackerMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated:
            return None

        try:
            match = resolve(request.path_info)
            view_name = match.view_name
        except:
            return None

        key = f"link_clicks:{request.user.id}"

        # ✅ 关键修复点：确保 defaultdict 包装
        cached = cache.get(key) or {}
        data = defaultdict(int, cached)

        data[view_name] += 1

        cache.set(key, dict(data), timeout=60 * 60 * 24 * 7)
        return None


class NavigationUsageMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        try:
            view_name = resolve(request.path_info).url_name
            if not view_name:
                return None

            if 'nav_clicks' not in request.session:
                request.session['nav_clicks'] = {}

            nav_clicks = request.session['nav_clicks']
            nav_clicks[view_name] = nav_clicks.get(view_name, 0) + 1
            request.session['nav_clicks'] = nav_clicks
        except Exception as e:
            pass  # 可以在调试时加日志 log.warning(f"中间件异常: {e}")

        return None



# ========== [BEGIN INSERT BLOCK M1] ==========
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

def _is_site_admin(user):
    """
    与 accounts/views.py 中一致的容错判断：
    - 超级用户
    - user.userprofile.is_system_admin
    - user.userprofile.is_staffbook_admin
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    up = getattr(user, "userprofile", None)
    if up:
        if getattr(up, "is_system_admin", False):
            return True
        if getattr(up, "is_staffbook_admin", False):
            return True
    return False


class SystemClosedMiddleware:
    """
    当 settings.SYSTEM_CLOSED=True 时：
    - 非管理员用户访问任何页面 → 统一跳转到 /closed/
    - 管理员用户不受影响（全站可用）
    - 白名单：/closed/、/accounts/login/、/accounts/logout/、静态/媒体资源、管理后台登录页等
    """
    def __init__(self, get_response):
        self.get_response = get_response

        # 白名单前缀（无需登录也允许访问）
        self.allowlist_prefixes = tuple(getattr(settings, "SYSTEM_CLOSED_ALLOWLIST_PREFIXES", [
            "/closed/",
            "/accounts/login/",
            "/accounts/logout/",
            "/accounts/password_reset",
            "/accounts/password_change",
            settings.STATIC_URL.rstrip("/"),
            settings.MEDIA_URL.rstrip("/") if getattr(settings, "MEDIA_URL", None) else "/media",
            "/admin/login/",
        ]))

    def __call__(self, request):
        # 若系统未关闭或当前用户是管理员 → 放行
        if not getattr(settings, "SYSTEM_CLOSED", False):
            return self.get_response(request)
        if _is_site_admin(getattr(request, "user", None)):
            return self.get_response(request)

        path = request.path or "/"

        # 避免死循环：暂停页自身放行
        try:
            closed_path = reverse("system_closed")
        except Exception:
            closed_path = "/closed/"
        if path.startswith(closed_path):
            return self.get_response(request)

        # 白名单前缀放行（登录/登出/静态/媒体/后台登录等）
        for prefix in self.allowlist_prefixes:
            if prefix and path.startswith(prefix):
                return self.get_response(request)

        # 其余全部拦截到暂停页
        return redirect("system_closed")
# ========== [END INSERT BLOCK M1] ==========
