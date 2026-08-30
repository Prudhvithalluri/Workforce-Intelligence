import logging
import smtplib
from email.message import EmailMessage

from config import settings

logger = logging.getLogger(__name__)


def send_wfh_notification(start_date: str, end_date: str, reason: str) -> None:
    """
    Sends a notification email confirming a submitted WFH request, using
    the values the user entered in the frontend (start_date, end_date,
    reason). Failure to send should never break the WFH flow, so all
    errors are caught and logged rather than raised.
    """
    if not settings.SMTP_HOST or not settings.SMTP_TO_EMAIL:
        logger.debug("wfh_email_skipped reason=smtp_not_configured")
        return

    employee_name = settings.SMTP_EMPLOYEE_NAME or "Employee"
    phone_line = (
        f"If anything urgent comes up, you can also reach me on my mobile "
        f"at {settings.SMTP_EMPLOYEE_PHONE}.\n\n"
        if settings.SMTP_EMPLOYEE_PHONE
        else ""
    )

    subject = f"Work From Home Request: {employee_name} - {start_date} to {end_date}"

    body = (
        f"Dear Team,\n\n"
        f"I am writing to request permission to work from home starting on "
        f"{start_date} through {end_date}.\n\n"
        f"I am requesting this arrangement because {reason}.\n\n"
        f"During this time, I will be fully equipped to handle my usual "
        f"responsibilities. I will be online during my regular working "
        f"hours, monitoring my emails, and attending all scheduled meetings.\n\n"
        f"{phone_line}"
        f"Please let me know if you have any questions or if you need me "
        f"to make any specific arrangements before I work remotely.\n\n"
        f"Thank you for your understanding and support.\n\n"
        f"Best regards,\n"
        f"{employee_name}"
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM_EMAIL
    msg["To"] = settings.SMTP_TO_EMAIL
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USERNAME:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("wfh_email_sent to=%s", settings.SMTP_TO_EMAIL)
    except Exception:
        logger.exception("wfh_email_failed")