"""Sending email over the company's own SMTP server (Gmail, Outlook/Microsoft 365, SES, Postmark...)."""

import smtplib
from email.message import EmailMessage

from gigscout.config import Settings

SMTP_TIMEOUT = 20
# Mail providers many unrelated people share: their domain says nothing about which company someone is from.
SHARED_MAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "hotmail.com", "hotmail.co.uk", "outlook.com",
    "live.com", "msn.com", "icloud.com", "me.com", "mac.com", "proton.me", "protonmail.com", "pm.me", "aol.com",
    "gmx.com", "gmx.de", "gmx.net", "web.de", "mail.com", "yandex.com", "yandex.ru", "zoho.com", "fastmail.com",
    "hey.com", "tutanota.com", "qq.com", "163.com", "naver.com",
})


def email_ready(settings: Settings) -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


def deliver(settings: Settings, message: EmailMessage) -> None:
    """Send one message from the configured sender (raises smtplib.SMTPException or OSError)."""
    if "From" not in message:
        message["From"] = settings.smtp_from
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password.get_secret_value())
        smtp.send_message(message)
