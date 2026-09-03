from datetime import datetime, timezone

from app.services.storage import remember_sheet_history


def test_remember_moves_url_to_front():
    older = {
        "url": "https://docs.google.com/spreadsheets/d/aaa/edit",
        "title": "Old",
        "used_at": "2026-01-01T00:00:00Z",
    }
    history = remember_sheet_history([older], "https://docs.google.com/spreadsheets/d/bbb/edit", "New")
    assert history[0]["url"].endswith("/bbb/edit")
    assert history[0]["title"] == "New"
    assert history[1]["url"] == older["url"]


def test_remember_dedupes_and_caps():
    items = [
        {"url": f"https://docs.google.com/spreadsheets/d/{i}/edit", "title": str(i), "used_at": "x"}
        for i in range(10)
    ]
    reused = items[3]["url"]
    history = remember_sheet_history(items, reused, "Again")
    assert len(history) == 8
    assert history[0]["url"] == reused
    assert history[0]["title"] == "Again"
    assert sum(1 for item in history if item["url"] == reused) == 1


def test_remember_ignores_blank():
    existing = [{"url": "https://example/sheet", "title": "A", "used_at": "x"}]
    assert remember_sheet_history(existing, "   ") == existing


def test_remember_sets_timestamp():
    history = remember_sheet_history([], "https://docs.google.com/spreadsheets/d/zzz/edit", "Z")
    used = datetime.fromisoformat(history[0]["used_at"].replace("Z", "+00:00"))
    assert used.tzinfo == timezone.utc
