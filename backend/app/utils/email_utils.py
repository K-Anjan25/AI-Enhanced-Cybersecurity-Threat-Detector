import smtplib
from email.message import EmailMessage
from app.core.config import settings


def send_email(subject: str, recipient: str, body: str) -> bool:
    """Send an email if SMTP is configured. Returns True on success, False otherwise."""
    if not settings.SMTP_HOST or not settings.SMTP_PORT or not settings.EMAIL_FROM:
        # SMTP not configured
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = recipient
    msg.set_content(body)

    try:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
        server.starttls()
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception:
        return False
