from app.routers.pipeline import _translation_targets


def test_empty_selection_translates_nothing():
    assert _translation_targets("en", []) == []
    assert _translation_targets("en", None) == []


def test_only_selected_languages():
    targets = _translation_targets("en", ["es", "hi", "fr"])
    names = {name for _, name in targets}
    assert names == {"Spanish", "Hindi", "French"}


def test_excludes_source_language():
    targets = _translation_targets("hi", ["hi", "en"])
    codes = {code for code, _ in targets}
    assert "hi" not in codes
    assert "en" in codes
