# common/context_processors.py
from .utils import get_most_common_links
from django.core.cache import cache

def common_links(request):
    most_common = get_most_common_links(top_n=5)
    return {
        'most_common_links': most_common
    }


def most_common_links(request):
    if not request.user.is_authenticated:
        return {}

    key = f"link_clicks:{request.user.id}"
    data = cache.get(key)

    if not data:
        return {}

    # 取前 3 个点击最多的链接名（view_name）
    sorted_items = sorted(data.items(), key=lambda x: x[1], reverse=True)
    top_views = [view_name for view_name, count in sorted_items[:3]]

    return {
        'most_common_links': top_views
    }