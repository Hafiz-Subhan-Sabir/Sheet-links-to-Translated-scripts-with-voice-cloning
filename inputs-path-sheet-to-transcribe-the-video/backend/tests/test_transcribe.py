from unittest.mock import patch

import pytest


@pytest.fixture
def mock_transcribe_result():
    return {
        "transcript": "[00:00] Hello world",
        "segments": [{"start": 0.0, "end": 1.0, "text": "Hello world", "confidence": 0.95}],
        "language": "en",
        "duration": 1.0,
        "confidence": 0.95,
    }


@patch("app.services.transcribe._transcribe_faster_whisper")
@patch("app.services.transcribe.prepare_local_audio")
def test_transcribe_local_mock(mock_prepare, mock_whisper, mock_transcribe_result):
    from app.services.transcribe import transcribe_source

    mock_prepare.return_value = ("/tmp/audio.mp3", 10.0)
    mock_whisper.return_value = {
        "transcript": mock_transcribe_result["transcript"],
        "segments": [{"start": 0.0, "end": 1.0, "text": "Hello world", "confidence": 0.95}],
        "language": "en",
        "duration": 1.0,
        "confidence": 0.95,
    }

    result = transcribe_source("/fake/path.mp3", "local", "en")
    assert "Hello world" in result["transcript"]
    assert result["language"] == "en"
