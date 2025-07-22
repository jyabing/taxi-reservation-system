from django import template

register = template.Library()

@register.filter
def jpycomma(value):
    try:
        value = float(value)
        return f"{value:,.0f}"
    except (ValueError, TypeError):
        return value
