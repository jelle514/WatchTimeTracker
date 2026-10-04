"""Tests for app name detection, mapping and source keys."""

import pytest

from custom_components.watch_time_tracker.app_names import (
    OverrideError,
    ResolvedApp,
    detect_app,
    make_key,
    parse_overrides,
    raw_app_values,
    resolve,
)


def test_builtin_lookup() -> None:
    assert resolve("com.netflix.ninja", {}) == ResolvedApp("netflix", "Netflix")


def test_builtin_lookup_ignores_case() -> None:
    assert resolve("COM.NETFLIX.NINJA", {}) == ResolvedApp("netflix", "Netflix")


def test_builtin_launcher_is_ignored() -> None:
    assert resolve("com.google.android.apps.tv.launcherx", {}) is None


def test_unknown_value_is_used_unchanged() -> None:
    assert resolve("NPO Start", {}) == ResolvedApp("npo_start", "NPO Start")


def test_override_beats_builtin() -> None:
    overrides = {"com.netflix.ninja": "Netflix NL"}
    assert resolve("com.netflix.ninja", overrides) == ResolvedApp(
        "netflix_nl", "Netflix NL"
    )


def test_override_can_ignore() -> None:
    assert resolve("Sonos Beam", {"sonos beam": None}) is None


def test_parse_overrides() -> None:
    text = "com.foo.bar = Foo\n\n  Sonos Beam = !ignore  \nPC=Gaming PC"
    assert parse_overrides(text) == {
        "com.foo.bar": "Foo",
        "sonos beam": None,
        "pc": "Gaming PC",
    }


@pytest.mark.parametrize(
    ("text", "line_number"),
    [("no equals sign", 1), ("ok = Fine\n= Missing raw", 2), ("raw =   ", 1)],
)
def test_parse_overrides_errors_name_the_line(text: str, line_number: int) -> None:
    with pytest.raises(OverrideError) as err:
        parse_overrides(text)
    assert err.value.line_number == line_number


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("YouTube", "youtube"),
        ("Disney+", "disney"),
        ("NPO Start", "npo_start"),
        ("Nintendo Switch Game Console", "nintendo_switch_game_console"),
        ("Crème Brûlée TV", "creme_brulee_tv"),
        ("Unknown app", "unknown_app"),
    ],
)
def test_make_key(name: str, key: str) -> None:
    assert make_key(name) == key


def test_make_key_empty_slug_uses_hash() -> None:
    key = make_key("📺")
    assert key.startswith("app_")
    assert len(key) == len("app_") + 8
    assert make_key("📺") == key
    assert make_key("🎮") != key


def test_raw_value_detection_order() -> None:
    media = {"app_name": "Netflix"}
    extra = {"current_activity": "com.google.android.youtube.tv", "source": "x"}
    assert raw_app_values(media, extra) == [
        "Netflix",
        "com.google.android.youtube.tv",
        "x",
    ]
    assert raw_app_values({"source": "PC", "app_name": "y"}, None) == ["PC", "y"]
    assert raw_app_values({}, {"source": "  ", "app_name": "Plex"}) == ["Plex"]
    assert raw_app_values({}, None) == []


def test_detect_app_uses_first_value() -> None:
    assert detect_app({"source": "PC"}, {"app_name": "Plex"}, {}) == (
        "PC",
        ResolvedApp("pc", "PC"),
    )


def test_detect_app_skips_ignored_values() -> None:
    # Observed: casting F1 TV to a Chromecast with Google TV. The Android TV
    # Remote player reports the Cast receiver; the Cast entity names the app.
    media = {"app_name": "com.google.android.apps.mediashell"}
    extra = {"app_name": "F1TV Chromecast"}
    assert detect_app(media, extra, {}) == (
        "F1TV Chromecast",
        ResolvedApp("f1tv_chromecast", "F1TV Chromecast"),
    )


def test_detect_app_all_ignored() -> None:
    launcher = "com.google.android.apps.tv.launcherx"
    assert detect_app({"app_name": launcher}, {"current_activity": launcher}, {}) == (
        launcher,
        None,
    )


def test_detect_app_nothing_to_detect() -> None:
    assert detect_app({}, None, {}) == (None, None)
