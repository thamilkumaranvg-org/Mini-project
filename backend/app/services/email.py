"""Email notification service with multi-provider abstraction (Console, Resend, SMTP)."""
from typing import Optional, Dict, Any
import httpx
from app.config import settings


def render_email_template(title: str, recipient_first_name: str, message: str, meta: Dict[str, Any]) -> str:
    """Generate clean responsive HTML email in the application color palette."""
    receipt_no = meta.get("receipt_no", "")
    session_info = meta.get("session_info", "")
    date_str = meta.get("date_str", "")
    extra_info = meta.get("extra_info", "")

    meta_html = ""
    if receipt_no:
        meta_html += f"<tr><td style='padding:6px 0;color:#6B675C;'>Receipt Number:</td><td style='font-weight:600;color:#2B2A26;'>{receipt_no}</td></tr>"
    if session_info:
        meta_html += f"<tr><td style='padding:6px 0;color:#6B675C;'>Session:</td><td style='font-weight:600;color:#2B2A26;'>{session_info}</td></tr>"
    if date_str:
        meta_html += f"<tr><td style='padding:6px 0;color:#6B675C;'>Date:</td><td style='font-weight:600;color:#2B2A26;'>{date_str}</td></tr>"
    if extra_info:
        meta_html += f"<tr><td style='padding:6px 0;color:#6B675C;'>Details:</td><td style='font-weight:600;color:#2E7D32;'>{extra_info}</td></tr>"

    meta_box = ""
    if meta_html:
        meta_box = f"""
        <div style="background-color:#FBF8F1;border:1px solid #E4DFD0;border-radius:8px;padding:16px;margin:20px 0;">
          <table width="100%" style="font-size:14px;border-collapse:collapse;">
            {meta_html}
          </table>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>{title}</title>
    </head>
    <body style="margin:0;padding:0;background-color:#FBF8F1;font-family:'Poppins',system-ui,-apple-system,sans-serif;color:#2B2A26;">
      <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#FBF8F1;padding:24px 0;">
        <tr>
          <td align="center">
            <table width="92%" max-width="560px" cellpadding="0" cellspacing="0" style="max-width:560px;background-color:#FFFFFF;border-radius:12px;border:1px solid #E4DFD0;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,0.04);">
              <tr>
                <td style="background-color:#1B5E20;padding:24px 28px;text-align:left;">
                  <h1 style="margin:0;color:#FFFFFF;font-size:20px;font-weight:600;letter-spacing:0.3px;">🌾 Farmer Produce Selling Portal</h1>
                  <p style="margin:4px 0 0 0;color:#E8F5E9;font-size:13px;">Official Slot Booking System</p>
                </td>
              </tr>
              <tr>
                <td style="padding:28px;">
                  <h2 style="margin:0 0 12px 0;color:#1B5E20;font-size:18px;">{title}</h2>
                  <p style="margin:0 0 16px 0;font-size:15px;line-height:1.6;color:#2B2A26;">Hello {recipient_first_name},</p>
                  <p style="margin:0 0 20px 0;font-size:15px;line-height:1.6;color:#2B2A26;">{message}</p>
                  {meta_box}
                  <p style="margin:24px 0 0 0;font-size:13px;line-height:1.5;color:#6B675C;">
                    Please present your booking QR code at the entrance during your booked session.
                    Do not share your booking details with anyone else.
                  </p>
                </td>
              </tr>
              <tr>
                <td style="background-color:#FBF8F1;border-top:1px solid #E4DFD0;padding:16px 28px;text-align:center;font-size:12px;color:#6B675C;">
                  Farmer Slot Booking Office • Asia/Kolkata Business Hours
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """


async def send_email_async(
    to_email: str,
    subject: str,
    title: str,
    recipient_first_name: str,
    message: str,
    meta: Optional[Dict[str, Any]] = None
) -> tuple[bool, Optional[str]]:
    """Send an email using configured provider. Returns (success, error_message)."""
    meta = meta or {}
    html_content = render_email_template(title, recipient_first_name, message, meta)

    provider = settings.EMAIL_PROVIDER.lower()

    if provider == "console":
        print(f"[CONSOLE EMAIL] To: {to_email} | Subject: {subject} | Title: {title}")
        return True, None

    elif provider == "resend":
        if not settings.RESEND_API_KEY:
            return False, "RESEND_API_KEY is not configured"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                    json={
                        "from": settings.EMAIL_FROM,
                        "to": [to_email],
                        "subject": subject,
                        "html": html_content
                    }
                )
                if res.status_code in (200, 201):
                    return True, None
                return False, f"Resend API error: {res.text}"
        except Exception as e:
            return False, str(e)

    elif provider == "smtp":
        if not settings.SMTP_HOST:
            return False, "SMTP_HOST is not configured"
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = settings.EMAIL_FROM
            msg["To"] = to_email
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                server.starttls()
                if settings.SMTP_USER and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.EMAIL_FROM, [to_email], msg.as_string())
            return True, None
        except Exception as e:
            return False, str(e)

    return False, f"Unknown email provider: {provider}"
