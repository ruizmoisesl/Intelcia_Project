"""Envío de correo vía SMTP (Gmail por defecto).

- Gmail requiere CONTRASEÑA DE APLICACIÓN (2FA activo); ver .env.example.
- Puerto 587 (STARTTLS); si SMTP_PORT=465 se usa SSL automáticamente.
- El threading de Gmail lo resuelven las cabeceras Message-ID / In-Reply-To /
  References, que añade notification_service.
- FAIL-SOFT: cualquier fallo se registra y devuelve False; nunca rompe la
  operación de negocio que originó el correo.
"""
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(settings.SMTP_USER and settings.SMTP_PASSWORD and settings.NOTIFICATIONS_ENABLED)


def _smtp_send(message: EmailMessage) -> None:
    """Envío real (indirección para pruebas)."""
    use_ssl = settings.SMTP_PORT == 465
    smtp = (
        smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
        if use_ssl
        else smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
    )
    try:
        if not use_ssl:
            smtp.starttls()
        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(message)
    finally:
        smtp.quit()


def send_email(
    *,
    to: str,
    subject: str,
    html: str,
    text: str,
    headers: dict[str, str] | None = None,
) -> bool:
    """Envía un correo. Devuelve True si se envió; False si no está
    configurado o falló (siempre se registran las causas)."""
    if not is_configured():
        logger.debug("SMTP no configurado: se omite «%s» para %s", subject, to)
        return False

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM or settings.SMTP_USER
    message["To"] = to
    message["Subject"] = subject
    for name, value in (headers or {}).items():
        message[name] = value
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    try:
        _smtp_send(message)
        return True
    except Exception as exc:  # fail-soft: nunca rompe el flujo
        logger.warning("No se pudo enviar «%s» a %s: %s", subject, to, exc)
        return False