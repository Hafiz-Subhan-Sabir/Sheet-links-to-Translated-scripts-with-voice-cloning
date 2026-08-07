"""Tests for input sheet column mapping."""

from app.services.input_sheet import _column_map


def test_column_map_standard_headers():
    headers = ["Program Title", "Video Path", "Status", "Error"]
    col = _column_map(headers)
    assert col["program title"] == 0
    assert col["video path"] == 1
    assert col["status"] == 2
    assert col["error"] == 3


def test_column_map_accepts_video_name_header():
    headers = ["Video Name", "Video Path", "Status", "Error"]
    col = _column_map(headers)
    assert col["program title"] == 0
    assert col["video path"] == 1


def test_column_map_accepts_url_alias():
    headers = ["Title", "URL", "Status", "Error"]
    col = _column_map(headers)
    assert col["program title"] == 0
    assert col["video path"] == 1
