"""Image processing utilities."""

import base64
import io
from datetime import datetime
from typing import Any

import cv2
import numpy as np
from PIL import ExifTags, Image


def encode_image_base64(image_bytes: bytes) -> str:
    """Encode image bytes to base64 string.

    Args:
        image_bytes: Raw image file bytes.

    Returns:
        Base64-encoded string.
    """
    return base64.b64encode(image_bytes).decode("utf-8")


def _convert_gps_to_degrees(gps_coord: tuple) -> float:
    """Convert GPS coordinate tuple (degrees, minutes, seconds) to decimal degrees.

    Args:
        gps_coord: Tuple of (degrees, minutes, seconds), each as (num, denom) rational.

    Returns:
        Decimal degrees as float.
    """
    d, m, s = gps_coord
    degrees = float(d[0]) / float(d[1]) if isinstance(d, tuple) else float(d)
    minutes = float(m[0]) / float(m[1]) if isinstance(m, tuple) else float(m)
    seconds = float(s[0]) / float(s[1]) if isinstance(s, tuple) else float(s)
    return degrees + (minutes / 60.0) + (seconds / 3600.0)


def _extract_gps(exif: dict[str, Any]) -> dict[str, float] | None:
    """Extract GPS coordinates from EXIF data.

    Args:
        exif: EXIF data dictionary from PIL.

    Returns:
        Dict with 'latitude', 'longitude', and optional 'altitude' keys,
        or None if GPS data is not present.
    """
    gps_info = exif.get("GPSInfo")
    if not gps_info:
        return None

    try:
        # GPS tags: 2=Latitude, 4=Longitude, 6=Altitude
        gps_tags = {v: k for k, v in ExifTags.GPSTAGS.items()}

        lat_tag = gps_tags.get("GPSLatitude")
        lat_ref_tag = gps_tags.get("GPSLatitudeRef")
        lon_tag = gps_tags.get("GPSLongitude")
        lon_ref_tag = gps_tags.get("GPSLongitudeRef")

        if lat_tag not in gps_info or lon_tag not in gps_info:
            return None

        latitude = _convert_gps_to_degrees(gps_info[lat_tag])
        longitude = _convert_gps_to_degrees(gps_info[lon_tag])

        # Apply reference direction (S/W are negative)
        lat_ref = gps_info.get(lat_ref_tag, "N")
        if isinstance(lat_ref, bytes):
            lat_ref = lat_ref.decode("utf-8")
        if lat_ref == "S":
            latitude = -latitude

        lon_ref = gps_info.get(lon_ref_tag, "E")
        if isinstance(lon_ref, bytes):
            lon_ref = lon_ref.decode("utf-8")
        if lon_ref == "W":
            longitude = -longitude

        result: dict[str, float] = {
            "latitude": round(latitude, 6),
            "longitude": round(longitude, 6),
        }

        # Optional altitude
        alt_tag = gps_tags.get("GPSAltitude")
        alt_ref_tag = gps_tags.get("GPSAltitudeRef")
        if alt_tag in gps_info:
            alt = gps_info[alt_tag]
            altitude = float(alt[0]) / float(alt[1]) if isinstance(alt, tuple) else float(alt)
            # GPSAltitudeRef: 0 = above sea level, 1 = below
            alt_ref = gps_info.get(alt_ref_tag, 0)
            if alt_ref == 1:
                altitude = -altitude
            result["altitude"] = round(altitude, 2)

        return result
    except (KeyError, IndexError, TypeError, ZeroDivisionError):
        return None


def _extract_capture_time(exif: dict[str, Any]) -> datetime | None:
    """Extract capture time from EXIF data.

    Args:
        exif: EXIF data dictionary from PIL.

    Returns:
        datetime object or None if not available.
    """
    for tag in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
        raw = exif.get(tag)
        if raw:
            try:
                return datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S")
            except (ValueError, TypeError):
                continue
    return None


def get_image_metadata(image_bytes: bytes) -> dict[str, Any]:
    """Extract image metadata including EXIF GPS and capture time."""
    img = Image.open(io.BytesIO(image_bytes))
    metadata: dict[str, Any] = {
        "width": img.width,
        "height": img.height,
        "format": img.format,
        "mode": img.mode,
        "file_size": len(image_bytes),
    }

    # Extract EXIF
    exif_data: dict[str, Any] = {}
    raw_exif = None
    if hasattr(img, "getexif"):
        try:
            raw_exif = img.getexif()
        except Exception:
            raw_exif = None
    if raw_exif:
        for tag_id, value in raw_exif.items():
            tag = ExifTags.TAGS.get(tag_id, tag_id)
            exif_data[str(tag)] = str(value)
    metadata["exif"] = exif_data

    # Extract GPS from raw EXIF (before string conversion)
    if raw_exif:
        gps = _extract_gps(dict(raw_exif))
        if gps:
            metadata["gps"] = gps

        capture_time = _extract_capture_time(dict(raw_exif))
        if capture_time:
            metadata["capture_time"] = capture_time.isoformat()

    return metadata


def auto_rotate(img: Image.Image) -> Image.Image:
    """Auto-rotate image based on EXIF orientation tag."""
    try:
        exif = img.getexif() if hasattr(img, "getexif") else None
        if exif:
            for tag_id, value in exif.items():
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                if tag == "Orientation":
                    if value == 3:
                        img = img.rotate(180, expand=True)
                    elif value == 6:
                        img = img.rotate(270, expand=True)
                    elif value == 8:
                        img = img.rotate(90, expand=True)
    except (AttributeError, KeyError):
        pass
    return img


def compress_image(
    image_bytes: bytes,
    max_size: tuple[int, int] = (2048, 2048),
    quality: int = 85,
) -> bytes:
    """Compress image to fit within max_size while maintaining aspect ratio."""
    img: Image.Image = Image.open(io.BytesIO(image_bytes))
    img = auto_rotate(img)

    # Resize if larger than max_size
    if img.width > max_size[0] or img.height > max_size[1]:
        img.thumbnail(max_size, Image.Resampling.LANCZOS)

    # Convert to RGB if necessary
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    output = io.BytesIO()
    img.save(output, format="JPEG", quality=quality, optimize=True)
    return output.getvalue()


def assess_sharpness(image_bytes: bytes) -> float:
    """Assess image sharpness using Laplacian variance.

    Higher values indicate sharper images. Typical thresholds:
    - < 100: very blurry
    - 100-500: slightly blurry
    - 500-1000: acceptable
    - > 1000: sharp

    Args:
        image_bytes: Raw image file bytes.

    Returns:
        Laplacian variance as float. Returns 0.0 for invalid input.
    """
    if not image_bytes:
        return 0.0

    try:
        # Decode image bytes to numpy array
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return 0.0

        # Compute Laplacian and return variance
        laplacian = cv2.Laplacian(img, cv2.CV_64F)
        return float(laplacian.var())
    except Exception:
        return 0.0


def is_blurry(image_bytes: bytes, threshold: float = 100.0) -> bool:
    """Check if image is blurry based on Laplacian variance threshold.

    Args:
        image_bytes: Raw image file bytes.
        threshold: Sharpness threshold. Below this value is considered blurry.

    Returns:
        True if image is blurry (sharpness below threshold).
    """
    return assess_sharpness(image_bytes) < threshold


def detect_image_format(image_bytes: bytes) -> str:
    """Detect image format from magic bytes.

    Args:
        image_bytes: Raw image file bytes.

    Returns:
        Image format string: 'png', 'gif', 'webp', or 'jpeg' (default).
    """
    if not image_bytes:
        return "jpeg"
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if image_bytes[:4] == b"GIF8":
        return "gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "webp"
    return "jpeg"

