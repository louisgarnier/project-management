import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

import pytest
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient


def test_transcribe_audio_returns_text():
    """transcribe_audio calls mlx_whisper.transcribe and returns stripped text."""
    from transcription.transcribe import transcribe_audio

    with patch("transcription.transcribe.mlx_whisper") as mock_mlx:
        mock_mlx.transcribe.return_value = {"text": "  Hello world  "}
        result = transcribe_audio("/fake/audio.mp3", "call.mp3")

    assert result == "Hello world"
    mock_mlx.transcribe.assert_called_once_with(
        "/fake/audio.mp3",
        path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
    )


def test_transcribe_audio_logs_filename():
    """transcribe_audio logs the filename at start."""
    from transcription.transcribe import transcribe_audio

    with patch("transcription.transcribe.mlx_whisper") as mock_mlx, \
         patch("transcription.transcribe.logger") as mock_logger:
        mock_mlx.transcribe.return_value = {"text": "hello"}
        transcribe_audio("/fake/audio.mp3", "my_call.mp3")

    all_log_calls = " ".join(str(c) for c in mock_logger.info.call_args_list)
    assert "my_call.mp3" in all_log_calls


@pytest.fixture
def client():
    """TestClient with model loading mocked — lifespan won't touch GPU/disk."""
    with patch("transcription.main.preload_model"):
        from transcription.main import app
        with TestClient(app) as c:
            yield c


def test_transcribe_api_mp3_only(client):
    """POST a non-mp3 file → 422."""
    r = client.post(
        "/transcribe",
        files={"audio": ("notes.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 422
    assert "mp3" in r.json()["detail"].lower()


def test_transcribe_api_happy_path(client):
    """POST an mp3 → {transcript, filename}."""
    with patch("transcription.main.transcribe_audio", return_value="Clean transcript text"):
        r = client.post(
            "/transcribe",
            files={"audio": ("call.mp3", b"fake-audio", "audio/mpeg")},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["transcript"] == "Clean transcript text"
    assert data["filename"] == "call.mp3"
