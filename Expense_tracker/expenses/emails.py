from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from django.conf import settings


def send_welcome_email(user_email, user_name):
    subject = "Welcome to Expense Tracker"
    text_content = f"Welcome, {user_name}! Thanks for signing up."
    html_content = render_to_string('emails/welcome.html', {
        'user_name': user_name,
        'site_url': 'http://127.0.0.1:8000/',
    })

    msg = EmailMultiAlternatives(subject, text_content, 'ajaylegend506@gmail.com', [user_email])
    msg.attach_alternative(html_content, "text/html")
    msg.send()


def send_otp_email(user_email, user_name, otp_code):
    subject = "Your Expense Tracker Verification Code"
    text_content = f"Your OTP is {otp_code}. It expires in 10 minutes."
    html_content = render_to_string('emails/otp_email.html', {
        'user_name': user_name,
        'otp_code': otp_code,
    })

    msg = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, [user_email])
    msg.attach_alternative(html_content, "text/html")
    msg.send()