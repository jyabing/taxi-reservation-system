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
