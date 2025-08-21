from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from accounts.models import DriverUser
from vehicles.models import Reservation, ReservationStatus

def send_notification(subject, message, to_emails=None, html_message=None, fail_silently=False):
    """
    通用邮件通知函数。
    参数：
    - subject: 邮件标题
    - message: 纯文本正文
    - to_emails: 收件人列表（可选，默认发给 DEFAULT_NOTIFICATION_EMAIL）
    - html_message: HTML 格式正文（可选）
    """
    if to_emails is None:
        to_emails = [getattr(settings, 'DEFAULT_NOTIFICATION_EMAIL', settings.DEFAULT_FROM_EMAIL)]

    send_mail(
        subject=subject,
        message=message.strip(),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=to_emails,
        html_message=html_message,
        fail_silently=fail_silently,
    )


def notify_admin_about_new_reservation(reservation):
    """
    向所有希望接收通知的管理员发送邮件，提醒有新的预约需要审批。
    """
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

    send_notification(subject, plain_message, to_emails=recipient_list, html_message=html_message)

def notify_driver_reservation_approved(reservation):
    """
    向司机本人发送邮件，告知预约已被审批通过。
    """
    driver = reservation.driver
    if not driver.email:
        return  # 没有邮件地址就跳过

    subject = f"【预约通过】你的车辆预约已获批准"
    plain_message = f"""你的预约已获批准：

车辆：{reservation.vehicle}
日期：{reservation.date.strftime('%Y-%m-%d')} ~ {reservation.end_date.strftime('%Y-%m-%d')}
时间：{reservation.start_time.strftime('%H:%M')} ~ {reservation.end_time.strftime('%H:%M')}
用途：{reservation.purpose}

请按时使用车辆，谢谢。
"""

    html_message = f"""
    <p>你的预约已获批准：</p>
    <ul>
      <li><strong>车辆：</strong> {reservation.vehicle}</li>
      <li><strong>日期：</strong> {reservation.date.strftime('%Y-%m-%d')} ~ {reservation.end_date.strftime('%Y-%m-%d')}</li>
      <li><strong>时间：</strong> {reservation.start_time.strftime('%H:%M')} ~ {reservation.end_time.strftime('%H:%M')}</li>
      <li><strong>用途：</strong> {reservation.purpose}</li>
    </ul>
    <p>请按时使用车辆，谢谢！</p>
    """

    send_notification(
        subject,
        plain_message,
        to_emails=[driver.email],
        html_message=html_message
    )

def mark_linked_reservation_incomplete(report, acting_user, mark_flag: bool):
    """
    仅当 mark_flag=True 且操作者为管理员时，
    将与日报同车、覆盖当日的预约标记为 INCOMPLETE（未完成出入库手续）。
    不填写 actual_return；司机在“入库”动作发生时，系统会改成 DONE。
    """
    if not mark_flag:
        return
    if not getattr(acting_user, "is_staff", False):
        return

    # report.driver 可能是 Driver 模型，取其 user；如本身就是 User，则原样返回
    driver_user = getattr(report.driver, "user", report.driver)

    linked = (
        Reservation.objects
        .filter(
            driver=driver_user,
            vehicle=report.vehicle,
            date__lte=report.date,
            end_date__gte=report.date,
        )
        .order_by("-date", "-start_time")
        .first()
    )
    if linked:
        linked.status = ReservationStatus.INCOMPLETE
        linked.save(update_fields=["status"])
# === mark_linked_reservation_incomplete: END ===