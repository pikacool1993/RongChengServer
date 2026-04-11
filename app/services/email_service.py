from __future__ import annotations

import logging
import os
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

logger = logging.getLogger(__name__)


def send_email(target_mail: str, mail_content: str) -> None:
    sender_name = os.getenv("SMTP_SENDER_NAME", "凤凰山票务")
    sender_email = os.getenv("SMTP_USER")
    sender_password = os.getenv("SMTP_PASSWORD")

    smtp_server = os.getenv("SMTP_HOST", "smtp.qq.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))  # SSL

    if not sender_email or not sender_password:
        logger.info("SMTP 未配置，已跳过发信。")
        return

    msg = MIMEMultipart()
    msg["From"] = formataddr((Header(sender_name, "utf-8").encode(), sender_email))
    msg["To"] = target_mail
    msg["Subject"] = Header("购票成功", "utf-8")

    body = MIMEText(mail_content, "html", "utf-8")
    msg.attach(body)

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, [target_mail], msg.as_string())
        logger.info("邮件发送成功", extra={"to": target_mail})
    except Exception:
        logger.exception("邮件发送失败", extra={"to": target_mail})

