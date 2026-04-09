import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

from starlette.testclient import TestClient
from transcription.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


def test_transcribe_rejects_txt_file():
    from io import BytesIO
    response = client.post(
        "/transcribe",
        files={"audio": ("transcript.txt", BytesIO(b"hello world"), "text/plain")},
    )
    assert response.status_code == 422
