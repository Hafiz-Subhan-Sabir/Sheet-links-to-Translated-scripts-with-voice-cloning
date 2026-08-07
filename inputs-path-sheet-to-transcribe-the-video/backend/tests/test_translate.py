from unittest.mock import patch

import pytest


@patch("app.services.translate._translate_google_free")
def test_translate_free_mode(mock_free):
    from app.config import get_settings
    from app.services.translate import translate_text

    get_settings.cache_clear()
    mock_free.return_value = "Bonjour"

    with patch.dict("os.environ", {"GOOGLE_TRANSLATE_MODE": "free", "GOOGLE_TRANSLATE_API_KEY": ""}):
        get_settings.cache_clear()
        text, provider = translate_text("Hello", "fr", "en")

    assert text == "Bonjour"
    assert provider == "google_free"
    mock_free.assert_called_once()


@patch("app.services.translate._translate_google_cloud_api")
def test_translate_api_mode(mock_api):
    from app.config import get_settings
    from app.services.translate import translate_text

    mock_api.return_value = "Hola"

    with patch.dict(
        "os.environ",
        {"GOOGLE_TRANSLATE_MODE": "auto", "GOOGLE_TRANSLATE_API_KEY": "test-key"},
    ):
        get_settings.cache_clear()
        text, provider = translate_text("Hello", "es", "en")

    assert text == "Hola"
    assert provider == "google_api"
