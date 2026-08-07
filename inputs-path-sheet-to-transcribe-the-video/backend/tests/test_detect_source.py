import pytest

from app.services.detect_source import detect_source, validate_local_path


class TestDetectSource:
    def test_http_url(self):
        r = detect_source("https://youtube.com/watch?v=abc123")
        assert r["valid"] is True
        assert r["type"] == "online"

    def test_www_url(self):
        r = detect_source("www.youtube.com/watch?v=abc")
        assert r["valid"] is True
        assert r["type"] == "online"
        assert r["normalized"].startswith("https://")

    def test_youtu_be(self):
        r = detect_source("https://youtu.be/abc123")
        assert r["valid"] is True
        assert r["type"] == "online"

    def test_windows_path(self):
        r = detect_source(r"C:\Videos\lecture.mp4")
        assert r["valid"] is True
        assert r["type"] == "local"

    def test_unix_path(self):
        r = detect_source("/home/user/video.mkv")
        assert r["valid"] is True
        assert r["type"] == "local"

    def test_file_extension_only(self):
        r = detect_source("myvideo.webm")
        assert r["valid"] is True
        assert r["type"] == "local"

    def test_file_protocol(self):
        r = detect_source("file:///C:/Videos/test.mp4")
        assert r["valid"] is True
        assert r["type"] == "local"

    def test_empty(self):
        r = detect_source("")
        assert r["valid"] is False

    def test_ambiguous(self):
        r = detect_source("something random text")
        assert r["valid"] is False

    def test_vimeo(self):
        r = detect_source("https://vimeo.com/123456")
        assert r["valid"] is True
        assert r["type"] == "online"


class TestValidateLocalPath:
    def test_nonexistent(self, tmp_path):
        valid, msg = validate_local_path(str(tmp_path / "missing.mp4"))
        assert valid is False
        assert "not found" in msg.lower()
