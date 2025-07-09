# staffbook/services.py

from .models import Driver

def get_driver_info(driver_id):
    try:
        return Driver.objects.get(id=driver_id)
    except Driver.DoesNotExist:
        return None
