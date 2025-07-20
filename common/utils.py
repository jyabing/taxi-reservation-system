# common/utils.py
from collections import Counter
from .models import LinkClickLog

def get_most_common_links(top_n=5, days=30):
    from django.utils import timezone
    from datetime import timedelta

    recent_logs = LinkClickLog.objects.filter(timestamp__gte=timezone.now() - timedelta(days=days))
    counter = Counter()

    for log in recent_logs:
        key = (log.name.strip(), log.url)
        counter[key] += 1

    most_common = counter.most_common(top_n)
    return [(name, url) for (name, url), _ in most_common]
