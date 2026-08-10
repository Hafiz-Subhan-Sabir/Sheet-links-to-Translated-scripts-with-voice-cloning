"""Tests for input sheet column mapping and auto-normalization."""

from app.constants import BATCH_STATUS_PENDING, INPUT_SHEET_HEADERS
from app.services.input_sheet import (
    _column_map,
    default_video_name,
    plan_normalized_sheet,
)


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


def test_plan_leaves_ready_sheet_alone():
    values = [
        list(INPUT_SHEET_HEADERS),
        ["Clip", "https://youtu.be/abc", "pending", ""],
    ]
    assert plan_normalized_sheet(values) is None


def test_plan_rewrites_bare_youtube_url_list():
    values = [
        ["https://www.youtube.com/watch?v=aRVv5NLVRwE"],
        ["https://www.youtube.com/watch?v=mz6vfaWQQiI"],
    ]
    planned = plan_normalized_sheet(values)
    assert planned is not None
    assert planned[0] == list(INPUT_SHEET_HEADERS)
    assert planned[1][0] == "aRVv5NLVRwE"
    assert planned[1][1] == "https://www.youtube.com/watch?v=aRVv5NLVRwE"
    assert planned[1][2] == BATCH_STATUS_PENDING
    assert planned[2][0] == "mz6vfaWQQiI"
    assert planned[2][1] == "https://www.youtube.com/watch?v=mz6vfaWQQiI"


def test_plan_empty_sheet_gets_headers():
    assert plan_normalized_sheet([]) == [list(INPUT_SHEET_HEADERS)]


def test_plan_partial_url_header():
    values = [
        ["URL"],
        ["https://youtu.be/abc123"],
    ]
    planned = plan_normalized_sheet(values)
    assert planned is not None
    assert planned[0] == list(INPUT_SHEET_HEADERS)
    assert planned[1][0] == "abc123"
    assert planned[1][1] == "https://youtu.be/abc123"
    assert planned[1][2] == BATCH_STATUS_PENDING


def test_default_video_name_youtube_id():
    assert default_video_name("https://www.youtube.com/watch?v=aRVv5NLVRwE", 1) == "aRVv5NLVRwE"
    assert default_video_name("https://youtu.be/mz6vfaWQQiI", 2) == "mz6vfaWQQiI"
