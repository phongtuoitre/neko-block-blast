import smtplib
from email.message import EmailMessage

from server.config import get_smtp_settings


def send_password_reset_email(recipient: str, code: str):
    settings = get_smtp_settings()
    message = EmailMessage()
    message["Subject"] = "Mã xác thực đổi mật khẩu Neko Block Blast"
    message["From"] = (
        f"{settings['from_name']} <{settings['email_from']}>"
    )
    message["To"] = recipient
    message.set_content(
        "Mã xác thực đổi mật khẩu của bạn là: "
        f"{code}\n\nMã có hiệu lực trong 10 phút. "
        "Nếu bạn không yêu cầu đổi mật khẩu, hãy bỏ qua email này."
    )

    with smtplib.SMTP(settings["host"], settings["port"], timeout=15) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(settings["username"], settings["password"])
        smtp.send_message(message)
