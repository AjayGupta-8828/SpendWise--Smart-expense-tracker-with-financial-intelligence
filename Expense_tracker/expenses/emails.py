import logging

import requests
from django.template.loader import render_to_string
from django.conf import settings

logger = logging.getLogger(__name__)


def _send_email(recipient, subject, text_content, html_content):
    """Send mail through SendGrid's HTTPS API without blocking on SMTP."""
    api_key = settings.SENDGRID_API_KEY
    sender = settings.DEFAULT_FROM_EMAIL
    if not api_key or not sender:
        logger.error("Email was not sent: SendGrid configuration is incomplete.")
        return False

    payload = {
        "personalizations": [{"to": [{"email": recipient}]}],
        "from": {"email": sender},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text_content},
            {"type": "text/html", "value": html_content},
        ],
    }
    try:
        response = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as error:
        logger.error("SendGrid email request failed: %s", error)
        return False


def send_welcome_email(user_email, user_name):
    subject = "Welcome to Expense Tracker"
    text_content = f"Welcome, {user_name}! Thanks for signing up."
    html_content = render_to_string('emails/welcome.html', {
        'user_name': user_name,
        'site_url': 'https://spendwise-smart-expense-tracker.onrender.com/',
    })
    return _send_email(user_email, subject, text_content, html_content)


def send_otp_email(user_email, user_name, otp_code):
    subject = "Your Expense Tracker Verification Code"
    text_content = f"Your OTP is {otp_code}. It expires in 10 minutes."
    html_content = render_to_string('emails/otp_email.html', {
        'user_name': user_name,
        'otp_code': otp_code,
    })

    return _send_email(user_email, subject, text_content, html_content)
