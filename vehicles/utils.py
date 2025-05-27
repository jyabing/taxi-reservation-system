from django.core.mail import send_mail
from django.conf import settings
from accounts.models import DriverUser

def notify_admin_about_new_reservation(reservation):
    admins = DriverUser.objects.filter(
        is_staff=True,
        wants_notification=True,
        notification_email__isnull=False
    ).exclude(notification_email='')

    recipient_list = [admin.notification_email for admin in admins]
    if not recipient_list:
        return

    subject = f"【预约审批提醒】{reservation.driver.username} 提交了新的车辆预约申请"
    message = f"""有新的预约需要审批：

司机：{reservation.driver.username}
车辆：{reservation.vehicle}
日期：{reservation.date.strftime('%Y-%m-%d')}
时间：{reservation.start_time.strftime('%H:%M')} ~ {reservation.end_time.strftime('%H:%M')}
备注：{getattr(reservation, 'note', '')}

请尽快前往后台【预约审批】菜单审核。
"""

    send_mail(
        subject,
        message,
        getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
        recipient_list,
        fail_silently=False
    )
