"""Image processing utilities."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ExifTags


def get_image_metadata(image_bytes: bytes) -> dict:
    """Extract basic image metadata."""
    img = Image.open(io.BytesIO(image_bytes))
    metadata = {
        "width": img.width,
        "height": img.height,
        "format": img.format,
        "mode": img.mode,
        "file_size": len(image_bytes),
    }

    # Extract EXIF
    exif_data = {}
    if hasattr(img, "_getexif") and img._getexif():
        exif = img._getexif()
        for tag_id, value in exif.items():
            tag = ExifTags.TAGS.get(tag_id, tag_id)
            exif_data[str(tag)] = str(value)
    metadata["exif"] = exif_data

    return metadata


def auto_rotate(img: Image.Image) -> Image.Image:
    """Auto-rotate image based on EXIF orientation tag."""
    try:
        exif = img._getexif()
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
    img = Image.open(io.BytesIO(image_bytes))
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
