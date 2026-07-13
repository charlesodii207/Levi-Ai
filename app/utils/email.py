import os
import smtplib
import ssl
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")


def send_otp_email(receiver_email: str, otp: str):
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        raise Exception(f"Missing credentials. EMAIL_ADDRESS={EMAIL_ADDRESS}, EMAIL_PASSWORD={'set' if EMAIL_PASSWORD else 'not set'}")

    message = EmailMessage()
    message["Subject"] = "Levi AI Email Verification"
    message["From"] = EMAIL_ADDRESS
    message["To"] = receiver_email

    message.set_content(f"""
Welcome to Levi AI!

Your verification code is: {otp}

This code expires in 10 minutes.

Levi AI Team
""")

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as e:
        raise Exception(f"Gmail authentication failed: {e}")
    except smtplib.SMTPException as e:
        raise Exception(f"SMTP error: {e}")
    except Exception as e:
        raise Exception(f"Email error: {e}")