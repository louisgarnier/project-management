import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

import pytest
from unittest.mock import MagicMock, patch


def test_transcribe_audio_formats_lines_correctly():
    """transcribe_audio merges Whisper segments with diarization and formats [MM:SS] SPEAKER_X: text."""
    from transcription.transcribe import transcribe_audio

    # Two segments: one at 0s (SPEAKER_0 turn 0-5s), one at 65s (SPEAKER_1 turn 60-70s)
    mock_model = MagicMock()
    mock_model.transcribe.return_value = {
        "segments": [
            {"start": 0.0, "end": 2.5, "text": "Hello world"},
            {"start": 65.0, "end": 67.0, "text": "Good morning"},
        ]
    }

    turn_0 = MagicMock()
    turn_0.start, turn_0.end = 0.0, 5.0
    turn_1 = MagicMock()
    turn_1.start, turn_1.end = 60.0, 70.0
    mock_diarization = MagicMock()
    mock_diarization.itertracks.return_value = [
        (turn_0, None, "SPEAKER_0"),
        (turn_1, None, "SPEAKER_1"),
    ]
    mock_pipeline = MagicMock(return_value=mock_diarization)

    with patch("transcription.transcribe._whisper_model", mock_model), \
         patch("transcription.transcribe._diarization_pipeline", mock_pipeline):
        result = transcribe_audio("/fake/path.mp3", "call.mp3")

    assert "[00:00] SPEAKER_0: Hello world" in result
    assert "[01:05] SPEAKER_1: Good morning" in result
