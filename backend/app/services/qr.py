"""Opaque QR token generation and base64 PNG image rendering."""
import secrets
import io
import base64
import qrcode
from qrcode.image.pil import PilImage


def generate_opaque_qr_token() -> str:
    """Generate a single-use cryptographically secure opaque token (never personal data)."""
    return secrets.token_urlsafe(32)


def generate_qr_data_uri(token: str) -> str:
    """Generate base64 data URI PNG image for the given token."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(token)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#1B5E20", back_color="#FFFFFF")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64_str}"

