"""Basic tests for the API."""

from fastapi.testclient import TestClient

from vision_insight.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"


def test_analyze_requires_image():
    """Test that analyze endpoint rejects non-image files."""
    response = client.post(
        "/api/v1/analyze",
        files={"file": ("test.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 400


def test_report_not_found():
    response = client.get("/api/v1/report/nonexistent")
    assert response.status_code == 404
