# vehicles/utils/notify.py
from django.core.mail import send_mail
from django.utils import timezone

def send_notification(subject, plain_message, recipients, html_message=None, from_email=None, fail_silently=True):
    """
    简单邮件通知封装。
    用法（你在 views 中已使用）：send_notification(subject, plain, ['a@b.com'], html)
    """
    if not recipients:
        return 0
    return send_mail(
        subject=subject,
        message=plain_message or "",
        from_email=from_email or None,   # 默认为 DEFAULT_FROM_EMAIL
        recipient_list=recipients,
        html_message=html_message or None,
        fail_silently=fail_silently,
    )

def notify_driver_reservation_approved(reservation):
    """
    预约审批通过后的通知封装。
    你在 admin/views 里直接传入 reservation 调用即可。
    """
    driver = getattr(reservation, "driver", None)
    email = getattr(driver, "email", None)
    subject = "【预约通过】车辆预约已批准"
    plain = (
        f"您好，您的预约已通过：\n"
        f"- 车辆：{getattr(reservation.vehicle, 'license_plate', reservation.vehicle_id)}\n"
        f"- 日期：{reservation.date} ~ {reservation.end_date}\n"
        f"- 时间：{reservation.start_time.strftime('%H:%M')} - {reservation.end_time.strftime('%H:%M')}\n"
        f"- 审批时间：{timezone.localtime(getattr(reservation, 'approved_at', timezone.now())).strftime('%Y-%m-%d %H:%M')}\n"
    )
    html = f"""
    <p>您好，您的预约已通过：</p>
    <ul>
      <li><b>车辆：</b>{getattr(reservation.vehicle, 'license_plate', reservation.vehicle_id)}</li>
      <li><b>日期：</b>{reservation.date} ~ {reservation.end_date}</li>
      <li><b>时间：</b>{reservation.start_time.strftime('%H:%M')} - {reservation.end_time.strftime('%H:%M')}</li>
      <li><b>审批时间：</b>{timezone.localtime(getattr(reservation, 'approved_at', timezone.now())).strftime('%Y-%m-%d %H:%M')}</li>
    </ul>
    """
    if email:
        send_notification(subject, plain, [email], html)
