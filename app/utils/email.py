import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")


def send_otp_email(receiver_email: str, otp: str):
    """
    Sends a 6-digit OTP to the user's email.
    """

    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        raise Exception(
            "EMAIL_ADDRESS or EMAIL_PASSWORD is missing in the .env file."
        )

    message = EmailMessage()
    message["Subject"] = "Levi AI Email Verification"
    message["From"] = EMAIL_ADDRESS
    message["To"] = receiver_email

    message.set_content(
        f"""
Welcome to Levi AI!

Your verification code is:

{otp}

This code expires in 10 minutes.

If you didn't create this account, you can safely ignore this email.

Levi AI Team
"""
    )

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.starttls()
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(message)