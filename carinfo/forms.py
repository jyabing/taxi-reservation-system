from django import forms
from .models import Car

class CarForm(forms.ModelForm):
    class Meta:
        model = Car
        fields = '__all__'
        widgets = {
            'status': forms.Select(choices=Car.STATUS_CHOICES)
        }