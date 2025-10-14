# vehicles/utils/admin_notify.py
from django.core.mail import send_mail
from django.conf import settings

def notify_admin_about_new_reservation(reservation):
    """
    向管理员发送“新预约提交”通知邮件。
    """
    try:
        subject = "【车辆预约系统】新预约提交"
        driver_name = getattr(reservation.driver, "get_full_name", lambda: reservation.driver.username)()
        plain_message = (
            f"预约人：{driver_name}\n"
            f"车辆：{getattr(reservation.vehicle, 'license_plate', reservation.vehicle_id)}\n"
            f"日期：{reservation.date} ~ {reservation.end_date}\n"
            f"时间：{reservation.start_time.strftime('%H:%M')} - {reservation.end_time.strftime('%H:%M')}\n"
            f"用途：{getattr(reservation, 'purpose', '—')}\n"
        )
        html_message = f"""
        <p><b>有新的车辆预约提交：</b></p>
        <ul>
          <li><b>预约人：</b>{driver_name}</li>
          <li><b>车辆：</b>{getattr(reservation.vehicle, 'license_plate', reservation.vehicle_id)}</li>
          <li><b>日期：</b>{reservation.date} ~ {reservation.end_date}</li>
          <li><b>时间：</b>{reservation.start_time.strftime('%H:%M')} - {reservation.end_time.strftime('%H:%M')}</li>
          <li><b>用途：</b>{getattr(reservation, 'purpose', '—')}</li>
        </ul>
        """

        recipients = [getattr(settings, "ADMIN_EMAIL", "jiabing.msn@gmail.com")]
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=recipients,
            html_message=html_message,
            fail_silently=True,
        )
    except Exception as e:
        print(f"⚠️ 管理员通知发送失败: {e}")
