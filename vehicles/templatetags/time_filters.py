from django import template

register = template.Library()

@register.filter
def time_length(duration):
    if not duration:
        return "--:--"
    total_seconds = int(duration.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    return f"{hours}時間{minutes}分"