from django import forms
from .models import Car

class CarForm(forms.ModelForm):
    # ✅ 尺寸字段校验与美化
    length = forms.IntegerField(
        label='長さ（mm）',
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={
            'placeholder': '例：4460',
            'class': 'form-control'
        })
    )
    width = forms.IntegerField(
        label='幅（mm）',
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={
            'placeholder': '例：1740',
            'class': 'form-control'
        })
    )
    height = forms.IntegerField(
        label='高さ（mm）',
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={
            'placeholder': '例：1490',
            'class': 'form-control'
        })
    )

    class Meta:
        model = Car
        fields = [
            'name', 'license_plate', 'brand', 'model', 'year',
            'registration_number', 'first_registration_date',
            'engine_displacement', 'model_code', 'vehicle_weight',
            'length', 'width', 'height',  # ✅ 新增車両寸法字段
            'status', 'is_active', 'mileage', 'fuel_type', 'color',
            'inspection_date', 'insurance_end_date',
            'etc_device', 'fuel_card_number', 'pos_terminal_id', 'gps_device_id',
            'department', 'manager_name', 'manager_phone',
            'notes', 'image',
        ]
        labels = {
            'name': '車両名',
            'license_plate': 'ナンバープレート',
            'brand': 'ブランド',
            'model': 'モデル',
            'year': '製造年',
            'registration_number': '登録番号',
            'first_registration_date': '初度登録年月',
            'engine_displacement': '総排気量（L）',
            'model_code': '型式',
            'vehicle_weight': '車両重量（kg）',
            'length': '長さ（mm）',
            'width': '幅（mm）',
            'height': '高さ（mm）',
            'status': '車両状態',
            'is_active': '使用中かどうか',
            'mileage': '走行距離（km）',
            'fuel_type': '燃料の種類',
            'color': 'ボディカラー',
            'inspection_date': '車検満了日',
            'insurance_expiry': '保険満了日',
            'etc_device': 'ETC機器番号',
            'fuel_card_number': '燃料カード番号',
            'pos_terminal_id': '決済端末番号',
            'gps_device_id': 'GPS機器番号',
            'department': '所属部署',
            'manager_name': '管理者氏名',
            'manager_phone': '管理者電話番号',
            'notes': '備考',
            'image': '車両画像',
        }
        help_texts = {
            'length': '※ 長さ（ミリメートル単位）を入力してください',
            'width': '※ 幅（ミリメートル単位）を入力してください',
            'height': '※ 高さ（ミリメートル単位）を入力してください',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.DateInput)):
                field.widget.attrs.setdefault('class', 'form-control')
                if 'placeholder' not in field.widget.attrs:
                    field.widget.attrs['placeholder'] = f'例：{field.label}'

