from .models import DriverUser

def get_system_notification_recipients():
    admins = DriverUser.objects.filter(
        is_staff=True,
        wants_notification=True,
        notification_email__isnull=False
    ).exclude(notification_email='')

    return [admin.notification_email for admin in admins]