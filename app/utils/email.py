import os
import resend
from dotenv import load_dotenv

load_dotenv()

resend.api_key = os.getenv("RESEND_API_KEY")


def send_otp_email(receiver_email: str, otp: str):
    params: resend.Emails.SendParams = {
        "from": "Levi AI <onboarding@resend.dev>",
        "to": [receiver_email],
        "subject": "Levi AI — Email Verification",
        "html": f"""
        <div style="font-family: Inter, sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 24px; background: #080C14; color: #F0F4FF; border-radius: 16px;">
            <h1 style="font-size: 32px; font-weight: 900; letter-spacing: 8px; background: linear-gradient(135deg, #D4AF37, #3B82F6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 8px;">LEVI</h1>
            <p style="color: #8B9CC4; font-size: 14px; margin-bottom: 32px;">Your intelligent AI assistant</p>

            <h2 style="color: #F0F4FF; font-size: 20px; font-weight: 700; margin-bottom: 8px;">Verify your email</h2>
            <p style="color: #8B9CC4; font-size: 14px; margin-bottom: 32px;">Enter this code to complete your registration:</p>

            <div style="background: #0D1420; border: 1px solid rgba(59,130,246,0.2); border-radius: 12px; padding: 24px; text-align: center; margin-bottom: 32px;">
                <span style="font-size: 42px; font-weight: 900; letter-spacing: 12px; color: #3B82F6;">{otp}</span>
            </div>

            <p style="color: #3D4F72; font-size: 13px;">This code expires in <strong style="color: #8B9CC4;">10 minutes</strong>.</p>
            <p style="color: #3D4F72; font-size: 13px;">If you didn't create a Levi AI account, you can safely ignore this email.</p>

            <hr style="border: none; border-top: 1px solid rgba(255,255,255,0.06); margin: 24px 0;" />
            <p style="color: #3D4F72; font-size: 12px;">Levi AI · Built by Charles Odii Okechukwu</p>
        </div>
        """,
    }

    resend.Emails.send(params)
