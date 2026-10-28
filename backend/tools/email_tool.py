
import os
import smtplib
from email.message import EmailMessage

def send_email(to: str, subject: str, body: str) -> dict[str, str]:
    gmail_address = os.getenv("GMAIL_ADDRESS")
    app_password = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_address or not app_password:
        return {
            "ok": "false",
            "message": "Gmail is not configured. Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in backend/.env.",
        }

    message = EmailMessage()
    message["From"] = gmail_address
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
            server.starttls()
            server.login(gmail_address, app_password)
            server.send_message(message)

        return {"ok": "true", "message": "Email sent successfully."}

    except (smtplib.SMTPException, OSError) as error:
        return {
            "ok": "false",
            "message": f"Failed to send email: {error}",
        }
