import os
from email.message import EmailMessage
import ssl
import smtplib

from celery import Celery

CELERY_BROKER = os.getenv("CELERY_BROKER_URL", "")
CELERY_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "")

celery = None
if CELERY_BROKER:
    celery = Celery("unitaryx_email_tasks", broker=CELERY_BROKER, backend=CELERY_BACKEND or None)
    # Fail fast when the broker is unreachable (local dev with no Redis, or a
    # downed broker in prod) so the caller can fall back to a synchronous send
    # instead of blocking on connection retries. Without this, enqueuing mail
    # against a missing broker hangs and no email is ever delivered.
    celery.conf.broker_transport_options = {
        "socket_timeout": 3,
        "socket_connect_timeout": 3,
    }
    # Mail results are never read; ignoring them stops .delay() from subscribing
    # to the result backend, which blocks for a long time when Redis is down.
    celery.conf.task_ignore_result = True
    celery.conf.broker_connection_retry_on_startup = False
    celery.conf.broker_connection_max_retries = 0


def _smtp_send_message_local(msg: EmailMessage):
    """Send EmailMessage synchronously (copied logic)."""
    smtp_host = (os.getenv("SMTP_HOST") or "smtp.gmail.com").strip()
    smtp_port_raw = (os.getenv("SMTP_PORT") or "587").strip()
    smtp_user = (os.getenv("SMTP_USER") or "").strip()
    smtp_pass = (os.getenv("SMTP_PASS") or "").strip()
    smtp_use_tls = (os.getenv("SMTP_USE_TLS", "True").strip().lower() in ("1","true","yes","on"))
    smtp_use_ssl = (os.getenv("SMTP_USE_SSL", "False").strip().lower() in ("1","true","yes","on"))

    try:
        smtp_port = int(smtp_port_raw)
    except Exception as exc:
        raise RuntimeError("SMTP_PORT must be a valid integer") from exc

    if not smtp_user or not smtp_pass:
        raise RuntimeError("SMTP_USER/SMTP_PASS are not configured")

    use_ssl = smtp_use_ssl or smtp_port == 465
    if use_ssl:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20, context=ssl.create_default_context()) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        server.ehlo()
        if smtp_use_tls:
            if not server.has_extn("starttls"):
                raise RuntimeError("SMTP server does not support STARTTLS. Set SMTP_USE_TLS=False or SMTP_USE_SSL=True.")
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)


if celery:
    @celery.task(name="unitaryx.send_email", ignore_result=True)
    def send_email_task(subject, sender, recipient, text_body, html_body=None):
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipient
        msg.set_content(text_body)
        if html_body:
            msg.add_alternative(html_body, subtype="html")
        _smtp_send_message_local(msg)

    # export task reference
    send_email = send_email_task
else:
    def send_email(subject, sender, recipient, text_body, html_body=None):
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipient
        msg.set_content(text_body)
        if html_body:
            msg.add_alternative(html_body, subtype="html")
        _smtp_send_message_local(msg)
