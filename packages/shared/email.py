"""SMTP delivery for account verification and password recovery messages."""

import smtplib
from email.message import EmailMessage
from ssl import create_default_context

from packages.shared.settings import Settings


class EmailDeliveryError(RuntimeError):
    """Configured email delivery failed or is unavailable."""


def send_email(settings: Settings, *, recipient: str, subject: str, body: str) -> None:
    if not settings.smtp_host or not settings.smtp_from_email:
        raise EmailDeliveryError("SMTP email delivery is not configured")

    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    try:
        if settings.smtp_use_ssl:
            client_context = smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=10,
                context=create_default_context(),
            )
        else:
            client_context = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
        with client_context as client:
            client.ehlo()
            if not settings.smtp_use_ssl and settings.smtp_starttls:
                client.starttls(context=create_default_context())
                client.ehlo()
            elif not settings.smtp_use_ssl:
                raise EmailDeliveryError("SMTP encryption is required")
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError("SMTP email delivery failed") from exc
