from django.core.mail import send_mail
from django.conf import settings
from accounts.models import DriverUser
from django.urls import reverse

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

    approval_url = f"{settings.SITE_BASE_URL}{reverse('reservation_approval_list')}"

    plain_message = f"""有新的预约需要审批：

司机：{reservation.driver.username}
车辆：{reservation.vehicle}
日期：{reservation.date.strftime('%Y-%m-%d')}
时间：{reservation.start_time.strftime('%H:%M')} ~ {reservation.end_time.strftime('%H:%M')}
备注：{getattr(reservation, 'note', '')}

请前往：{approval_url} 查看详情。
"""

    html_message = f"""
    <p>有新的预约需要审批：</p>
    <ul>
      <li><strong>司机：</strong> {reservation.driver.username}</li>
      <li><strong>车辆：</strong> {reservation.vehicle}</li>
      <li><strong>日期：</strong> {reservation.date.strftime('%Y-%m-%d')}</li>
      <li><strong>时间：</strong> {reservation.start_time.strftime('%H:%M')} ~ {reservation.end_time.strftime('%H:%M')}</li>
      <li><strong>备注：</strong> {getattr(reservation, 'note', '')}</li>
    </ul>
    <p><a href="{approval_url}" style="color:white;background-color:#007BFF;padding:8px 12px;border-radius:4px;text-decoration:none;">点击前往审批页面</a></p>
    """

    send_mail(
        subject,
        plain_message,
        settings.DEFAULT_FROM_EMAIL,  # ✅ 明确使用配置值
        recipient_list,
        html_message=html_message,
        fail_silently=False
    )
