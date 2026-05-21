"""Tests for image utility functions."""

from __future__ import annotations

import io
from datetime import datetime

import cv2
import numpy as np
import pytest
from PIL import Image

from vision_insight.utils.image import (
    _convert_gps_to_degrees,
    _extract_capture_time,
    _extract_gps,
    assess_sharpness,
    auto_rotate,
    compress_image,
    get_image_metadata,
    is_blurry,
)

# === Helpers ===


def _piexif_available() -> bool:
    try:
        import piexif  # noqa: F401

        return True
    except ImportError:
        return False


def _make_jpeg_with_exif(gps: dict | None = None, datetime_str: str | None = None) -> bytes:
    """Create a JPEG image with EXIF data for testing."""
    img = Image.new("RGB", (200, 150), color="green")
    buf = io.BytesIO()

    try:
        import piexif

        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}

        if datetime_str:
            exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = datetime_str.encode()
            exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = datetime_str.encode()

        if gps:
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = gps.get("lat_ref", b"N")
            lat = gps.get("lat", ((35, 1), (41, 1), (5147, 100)))
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = lat
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = gps.get("lon_ref", b"E")
            lon = gps.get("lon", ((139, 1), (45, 1), (2167, 100)))
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = lon

        exif_bytes = piexif.dump(exif_dict)
        img.save(buf, format="JPEG", exif=exif_bytes)
    except ImportError:
        img.save(buf, format="JPEG", quality=90)

    return buf.getvalue()


def _make_synthetic_jpeg_bytes(width: int = 100, height: int = 100) -> bytes:
    """Create a synthetic JPEG using OpenCV."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.putText(img, "test", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    _, encoded = cv2.imencode(".jpg", img)
    return encoded.tobytes()


# === _convert_gps_to_degrees tests ===


class TestConvertGPSToDegrees:
    def test_tokyo_coordinates(self):
        # 35°41'51.47"N  139°45'21.67"E
        coord = ((35, 1), (41, 1), (5147, 100))
        result = _convert_gps_to_degrees(coord)
        assert abs(result - 35.6976) < 0.001

    def test_zero_coordinates(self):
        result = _convert_gps_to_degrees(((0, 1), (0, 1), (0, 1)))
        assert result == 0.0

    def test_float_input(self):
        """Handle plain float values (non-tuple)."""
        result = _convert_gps_to_degrees((35.0, 30.0, 0.0))
        assert abs(result - 35.5) < 0.001


# === _extract_gps tests ===


class TestExtractGPS:
    def test_no_gps_info(self):
        result = _extract_gps({})
        assert result is None

    def test_empty_gps_info(self):
        result = _extract_gps({"GPSInfo": {}})
        assert result is None

    def test_valid_gps_north_east(self):
        """Tokyo Tower coordinates."""
        from PIL.ExifTags import GPSTAGS

        gps_tags = {v: k for k, v in GPSTAGS.items()}
        gps_info = {
            gps_tags["GPSLatitudeRef"]: "N",
            gps_tags["GPSLatitude"]: ((35, 1), (41, 1), (5147, 100)),
            gps_tags["GPSLongitudeRef"]: "E",
            gps_tags["GPSLongitude"]: ((139, 1), (45, 1), (2167, 100)),
        }
        result = _extract_gps({"GPSInfo": gps_info})
        assert result is not None
        assert abs(result["latitude"] - 35.6976) < 0.01
        assert abs(result["longitude"] - 139.7560) < 0.01

    def test_south_west_coordinates(self):
        """Southern hemisphere, western hemisphere."""
        from PIL.ExifTags import GPSTAGS

        gps_tags = {v: k for k, v in GPSTAGS.items()}
        gps_info = {
            gps_tags["GPSLatitudeRef"]: "S",
            gps_tags["GPSLatitude"]: ((33, 1), (52, 1), (0, 1)),
            gps_tags["GPSLongitudeRef"]: "W",
            gps_tags["GPSLongitude"]: ((70, 1), (40, 1), (0, 1)),
        }
        result = _extract_gps({"GPSInfo": gps_info})
        assert result is not None
        assert result["latitude"] < 0
        assert result["longitude"] < 0


# === _extract_capture_time tests ===


class TestExtractCaptureTime:
    def test_valid_datetime(self):
        result = _extract_capture_time({"DateTimeOriginal": "2024:03:15 14:30:00"})
        assert result == datetime(2024, 3, 15, 14, 30, 0)

    def test_fallback_to_digitized(self):
        result = _extract_capture_time({"DateTimeDigitized": "2023:01:01 00:00:00"})
        assert result == datetime(2023, 1, 1, 0, 0, 0)

    def test_no_datetime(self):
        result = _extract_capture_time({})
        assert result is None

    def test_invalid_format(self):
        result = _extract_capture_time({"DateTimeOriginal": "not-a-date"})
        assert result is None


# === get_image_metadata tests ===


class TestGetImageMetadata:
    def test_basic_metadata(self, sample_png_bytes):
        meta = get_image_metadata(sample_png_bytes)
        assert meta["width"] == 100
        assert meta["height"] == 100
        assert meta["format"] == "PNG"
        assert meta["file_size"] > 0
        assert "exif" in meta

    def test_jpeg_metadata(self, sample_jpeg_bytes):
        meta = get_image_metadata(sample_jpeg_bytes)
        assert meta["format"] == "JPEG"

    @pytest.mark.skipif(not _piexif_available(), reason="piexif not installed")
    def test_gps_extraction(self):
        jpeg_bytes = _make_jpeg_with_exif(
            gps={
                "lat_ref": b"N",
                "lat": ((35, 1), (41, 1), (5147, 100)),
                "lon_ref": b"E",
                "lon": ((139, 1), (45, 1), (2167, 100)),
            },
            datetime_str="2024:03:15 14:30:00",
        )
        meta = get_image_metadata(jpeg_bytes)
        assert "gps" in meta
        assert abs(meta["gps"]["latitude"] - 35.6976) < 0.01
        assert "capture_time" in meta

    def test_no_exif(self, sample_png_bytes):
        meta = get_image_metadata(sample_png_bytes)
        assert meta.get("gps") is None
        assert meta.get("capture_time") is None


# === auto_rotate tests ===


class TestAutoRotate:
    def test_no_orientation(self):
        img = Image.new("RGB", (100, 50), "red")
        result = auto_rotate(img)
        assert result.size == (100, 50)

    def test_orientation_3(self):
        """180 degree rotation."""
        img = Image.new("RGB", (100, 50), "red")
        img._getexif = lambda: {274: 3}
        result = auto_rotate(img)
        assert result.size == (100, 50)

    def test_no_exif(self):
        img = Image.new("RGB", (100, 50), "red")
        if hasattr(img, "_getexif"):
            delattr(img, "_getexif")
        result = auto_rotate(img)
        assert result.size == (100, 50)


# === compress_image tests ===


class TestCompressImage:
    def test_basic_compression(self, sample_png_bytes):
        result = compress_image(sample_png_bytes, quality=50)
        assert isinstance(result, bytes)
        assert len(result) > 0
        assert result[:2] == b"\xff\xd8"

    def test_resize_large_image(self):
        img = Image.new("RGB", (4000, 3000), "red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        large_bytes = buf.getvalue()

        result = compress_image(large_bytes, max_size=(2048, 2048))
        result_img = Image.open(io.BytesIO(result))
        assert result_img.width <= 2048
        assert result_img.height <= 2048

    def test_rgba_to_rgb(self):
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        rgba_bytes = buf.getvalue()

        result = compress_image(rgba_bytes)
        result_img = Image.open(io.BytesIO(result))
        assert result_img.mode == "RGB"


# === assess_sharpness tests ===


class TestAssessSharpness:
    def test_empty_bytes(self):
        assert assess_sharpness(b"") == 0.0

    def test_invalid_bytes(self):
        assert assess_sharpness(b"not an image") == 0.0

    def test_sharp_image(self):
        """An image with text/edges should have high sharpness."""
        bytes_data = _make_synthetic_jpeg_bytes(200, 200)
        score = assess_sharpness(bytes_data)
        assert score > 0

    def test_blank_image_low_sharpness(self):
        """A blank uniform image should have very low sharpness."""
        img = np.full((200, 200, 3), 128, dtype=np.uint8)
        _, encoded = cv2.imencode(".jpg", img)
        score = assess_sharpness(encoded.tobytes())
        assert score < 10


# === is_blurry tests ===


class TestIsBlurry:
    def test_empty_bytes(self):
        assert is_blurry(b"") is True

    def test_invalid_bytes(self):
        assert is_blurry(b"garbage") is True

    def test_sharp_image_not_blurry(self):
        bytes_data = _make_synthetic_jpeg_bytes(200, 200)
        assert is_blurry(bytes_data, threshold=0.001) is False

    def test_custom_threshold(self):
        bytes_data = _make_synthetic_jpeg_bytes(200, 200)
        assert is_blurry(bytes_data, threshold=999999.0) is True
