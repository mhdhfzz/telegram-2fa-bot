import io
from typing import Optional
from PIL import Image
import qrcode


def encode_qr_image(data: str) -> bytes:
    """Generate a PNG byte array of the QR code for given string data."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def decode_qr_image(image_bytes: bytes) -> Optional[str]:
    """
    Decode QR code from image bytes.
    Tries pyzbar first; falls back to OpenCV if pyzbar fails or is unavailable.
    """
    # Attempt 1: pyzbar
    try:
        from pyzbar.pyzbar import decode as zbar_decode

        image = Image.open(io.BytesIO(image_bytes))
        decoded_objects = zbar_decode(image)
        if decoded_objects:
            return decoded_objects[0].data.decode("utf-8")
    except Exception:
        pass

    # Attempt 2: OpenCV QRCodeDetector fallback
    try:
        import cv2
        import numpy as np

        np_arr = np.frombuffer(image_bytes, np.uint8)
        img_cv = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img_cv is not None:
            detector = cv2.QRCodeDetector()
            data, _, _ = detector.detectAndDecode(img_cv)
            if data:
                return data
    except Exception:
        pass

    return None
