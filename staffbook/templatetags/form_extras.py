from django import template

register = template.Library()

@register.filter(name='add_class')
def add_class(field, css_classes):
    """
    向字段添加 CSS class（不会覆盖已有 class）。
    用法示例：
      {{ form.myfield|add_class:"form-control form-control-sm" }}
    """
    existing = field.field.widget.attrs.get('class', '')
    final_class = f"{existing} {css_classes}".strip()
    return field.as_widget(attrs={'class': final_class})


@register.filter(name='add_attr')
def add_attr(field, attr_string):
    """
    向字段添加任意属性，支持多个，用英文逗号分隔。
    用法示例：
      {{ form.myfield|add_attr:"type:number,step:1,inputmode:numeric" }}
    """
    attrs = {}
    for pair in attr_string.split(','):
        if ':' in pair:
            key, val = pair.split(':', 1)
            attrs[key.strip()] = val.strip()
    return field.as_widget(attrs=attrs)
