# accounts/utils.py
from functools import wraps
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import user_passes_test

def check_module_permission(module_name):
    """
    装饰器：根据模块名检查 user.userprofile 中是否有相应权限
    允许 'staffbook'（台账）、'vehicles'（配车）、'carinfo'（车辆）
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            profile = getattr(request.user, 'userprofile', None)
            if not profile:
                return HttpResponseForbidden("没有权限")

            # 对应字段映射
            field_map = {
                'staffbook': profile.is_staffbook_admin,
                'vehicles': profile.is_vehicles_admin,
                'carinfo': profile.is_carinfo_admin,
            }
            if module_name in field_map and field_map[module_name]:
                return view_func(request, *args, **kwargs)

            return HttpResponseForbidden("您没有权限访问此模块")
        return _wrapped_view
    return decorator
