from django import template

register = template.Library()

@register.filter
def get_total(totals, args):
    """
    使用 {{ totals|get_total:"uber,raw" }} 取得对应统计值
    """
    try:
        method, kind = args.split(',')
        return totals.get(f'{method}_{kind}', 0)
    except:
        return 0