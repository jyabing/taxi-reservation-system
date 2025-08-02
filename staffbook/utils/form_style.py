# staffbook/utils/form_style.py

def apply_form_control_style(form, exclude_fields=None):
    """
    为表单字段统一添加 Bootstrap 样式类。
    可选参数 exclude_fields 可用于跳过某些字段。
    """
    if exclude_fields is None:
        exclude_fields = []

    for field_name, field in form.fields.items():
        if field_name in exclude_fields:
            continue
        old_class = field.widget.attrs.get("class", "")
        if "form-control" not in old_class:
            field.widget.attrs["class"] = (old_class + " form-control").strip()
