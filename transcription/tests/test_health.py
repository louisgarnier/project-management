import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

import pytest
from unittest.mock import patch
from starlette.testclient import TestClient


@pytest.fixture
def client():
    with patch("transcription.main.preload_model"):
        from transcription.main import app
        with TestClient(app) as c:
            yield c


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "models": "loaded"}


def test_transcribe_rejects_txt_file(client):
    from io import BytesIO
    response = client.post(
        "/transcribe",
        files={"audio": ("transcript.txt", BytesIO(b"hello world"), "text/plain")},
    )
    assert response.status_code == 422
