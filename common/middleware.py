# common/middleware.py  (NEW FILE)
import re
from django.conf import settings
from django.urls import reverse
from django.shortcuts import redirect

class SystemClosedMiddleware:
    """
    当 settings.SYSTEM_CLOSED = True:
      - superuser/staff: 全放行
      - 未登录: 仅放行 SYSTEM_CLOSED_ALLOWLIST_PREFIXES
      - 已登录: 放行公共白名单 + SYSTEM_CLOSED_AUTH_ALLOWLIST_PREFIXES
      - 其他: 跳转 /closed/
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt_prefixes_public = [
            p.rstrip("/") for p in getattr(settings, "SYSTEM_CLOSED_ALLOWLIST_PREFIXES", [])
        ]
        self.exempt_prefixes_auth = [
            p.rstrip("/") for p in getattr(settings, "SYSTEM_CLOSED_AUTH_ALLOWLIST_PREFIXES", [])
        ]

    def __call__(self, request):
        # 如果没开关，直接过
        if not getattr(settings, "SYSTEM_CLOSED", False):
            return self.get_response(request)

        path = (request.path_info or "/").rstrip("/")

        # 永远放行 /closed/ 本身
        try:
            if path == reverse("system_closed").rstrip("/"):
                return self.get_response(request)
        except Exception:
            pass

        user = request.user

        # 1) 管理员无条件放行
        if user.is_authenticated and (user.is_superuser or user.is_staff):
            return self.get_response(request)

        # 2) 未登录：只能看公共白名单
        if not user.is_authenticated:
            if self._prefix_hit(path, self.exempt_prefixes_public):
                return self.get_response(request)
            return redirect(reverse("system_closed"))

        # 3) ✅ 登录了：先做一个“粗放行”
        #    只要是 /accounts/... 或 /dailyreport/... 都让进
        if (
            path.startswith("/accounts")
            or path.startswith("/dailyreport")
            or path.startswith("/vehicles/my_dailyreports") 
            or path.startswith("/vehicles/my_dailyreport")  # ← 这里改成你的真实路径
        ):
            return self.get_response(request)

        # 4) 正常的白名单判断
        if self._prefix_hit(path, self.exempt_prefixes_public) or \
           self._prefix_hit(path, self.exempt_prefixes_auth):
            return self.get_response(request)

        # 5) 其他一律拦截
        return redirect(reverse("system_closed"))

    @staticmethod
    def _prefix_hit(path: str, prefixes: list[str]) -> bool:
        for p in prefixes:
            if p and path.startswith(p):
                return True
        return False


# ======== [BEGIN INSERT BLOCK MW-STUBS] ========
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)

class LinkClickTrackerMiddleware:
    """
    极简埋点：当客户端向 /log-link-click/ POST 时，记录一条日志。
   （与你 base.html 的 fetch("/log-link-click/") 相呼应。没有对应 view 也不会报错。）
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            if request.path_info == "/log-link-click/" and request.method == "POST":
                link_name = (request.POST.get("link_name") or "").strip()
                link_url  = (request.POST.get("link_url") or "").strip()
                user = getattr(request, "user", None)
                user_repr = (getattr(user, "username", None) or "anonymous") if (user and user.is_authenticated) else "anonymous"
                logger.info(
                    "[link-click] user=%s name=%s url=%s ip=%s at=%s",
                    user_repr, link_name, link_url, request.META.get("REMOTE_ADDR"),
                    timezone.now().isoformat()
                )
        except Exception as e:
            logger.warning("LinkClickTrackerMiddleware error: %r", e)

        return self.get_response(request)


class NavigationUsageMiddleware:
    """
    极简导航使用记录：对所有请求打印一条 DEBUG 日志（默认不输出，因为 root level 为 INFO）。
    仅为满足 MIDDLEWARE 导入。后续你可改为写数据库/消息队列。
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            user = getattr(request, "user", None)
            user_repr = (getattr(user, "username", None) or "anonymous") if (user and user.is_authenticated) else "anonymous"
            logger.debug(
                "[nav-usage] user=%s path=%s method=%s at=%s",
                user_repr, request.path_info, request.method, timezone.now().isoformat()
            )
        except Exception as e:
            logger.debug("NavigationUsageMiddleware error: %r", e)

        return self.get_response(request)
# ======== [END INSERT BLOCK MW-STUBS] ========
