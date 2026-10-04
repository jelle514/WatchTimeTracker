"""Tests for the watch session state machine (fake clock, no HA)."""

import pytest

from custom_components.watch_time_tracker.const import (
    MODE_APP_OPEN,
    MODE_PLAYING_ONLY,
    UNKNOWN_APP_KEY,
)
from custom_components.watch_time_tracker.tracker import (
    Counting,
    Grace,
    Idle,
    Tracker,
    combined_player_state,
    counting_app,
    effective_mode,
)


def total(credits: list[tuple[str, float]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, minutes in credits:
        out[key] = out.get(key, 0) + minutes
    return out


def test_short_gap_is_fully_counted() -> None:
    t = Tracker(grace_period=60)
    credits = t.update("youtube", 0)
    credits += t.update(None, 300)  # gap between two videos
    credits += t.update("youtube", 320)
    credits += t.close(600)
    assert total(credits) == {"youtube": 10.0}


def test_gap_longer_than_grace_is_not_counted() -> None:
    t = Tracker(grace_period=60)
    t.update("youtube", 0)
    assert t.update(None, 120) == []
    assert isinstance(t.state, Grace)
    assert t.grace_expired() == [("youtube", 2.0)]
    assert t.state == Idle()


def test_switching_apps_during_grace_does_not_count_gap() -> None:
    t = Tracker(grace_period=60)
    t.update("youtube", 0)
    t.update(None, 60)
    assert t.update("netflix", 90) == [("youtube", 1.0)]
    assert t.state == Counting("netflix", 90)


def test_off_during_grace_keeps_grace() -> None:
    t = Tracker(grace_period=60)
    t.update("youtube", 0)
    t.update(None, 60)  # paused
    assert t.update(None, 70) == []  # off
    assert t.state == Grace("youtube", 0, 60)


def test_same_app_update_is_noop() -> None:
    t = Tracker(grace_period=60)
    t.update("youtube", 0)
    assert t.update("youtube", 30) == []
    assert t.state == Counting("youtube", 0)


def test_idle_not_counting_is_noop() -> None:
    t = Tracker(grace_period=60)
    assert t.update(None, 10) == []
    assert t.state == Idle()


def test_switching_apps_credits_previous() -> None:
    t = Tracker(grace_period=60)
    t.update("youtube", 0)
    assert t.update("netflix", 180) == [("youtube", 3.0)]


def test_grace_zero_closes_immediately() -> None:
    t = Tracker(grace_period=0)
    t.update("youtube", 0)
    assert t.update(None, 60) == [("youtube", 1.0)]
    assert t.state == Idle()


def test_live_ticks_do_not_double_count() -> None:
    t = Tracker(grace_period=60)
    t.update("youtube", 0)
    credits = t.tick(60) + t.tick(120)
    credits += t.update(None, 150)
    credits += t.grace_expired()
    assert total(credits) == pytest.approx({"youtube": 2.5})


def test_tick_during_grace_credits_nothing() -> None:
    t = Tracker(grace_period=60)
    t.update("youtube", 0)
    t.update(None, 30)
    assert t.tick(60) == []


def test_negative_difference_credits_nothing() -> None:
    t = Tracker(grace_period=0)
    t.update("youtube", 100)
    assert t.tick(50) == []
    assert t.update(None, 90) == []


def test_close_during_counting() -> None:
    t = Tracker(grace_period=60)
    t.update("youtube", 0)
    assert t.close(120) == [("youtube", 2.0)]
    assert t.state == Idle()


def test_close_during_grace_credits_up_to_gap_start() -> None:
    t = Tracker(grace_period=60)
    t.update("youtube", 0)
    t.update(None, 120)
    assert t.close(150) == [("youtube", 2.0)]


@pytest.mark.parametrize(
    ("state", "mode", "expected"),
    [
        ("playing", MODE_PLAYING_ONLY, "youtube"),
        ("paused", MODE_PLAYING_ONLY, None),
        ("on", MODE_PLAYING_ONLY, None),
        ("playing", MODE_APP_OPEN, "youtube"),
        ("paused", MODE_APP_OPEN, "youtube"),
        ("on", MODE_APP_OPEN, "youtube"),
        ("idle", MODE_APP_OPEN, "youtube"),
        ("off", MODE_APP_OPEN, None),
        ("standby", MODE_APP_OPEN, None),
        ("unavailable", MODE_APP_OPEN, None),
        ("unknown", MODE_APP_OPEN, None),
    ],
)
def test_counting_modes(state: str, mode: str, expected: str | None) -> None:
    assert counting_app(state, "youtube", mode, set()) == expected


def test_ignored_app_and_missing_player_never_count() -> None:
    assert counting_app("playing", None, MODE_PLAYING_ONLY, set()) is None
    assert counting_app("on", None, MODE_APP_OPEN, set()) is None
    assert counting_app(None, "youtube", MODE_APP_OPEN, set()) is None


def test_per_source_mode_on_one_tv() -> None:
    exceptions = {"pc"}
    # HDMI source counts while merely on; the app only while playing.
    assert counting_app("on", "pc", MODE_PLAYING_ONLY, exceptions) == "pc"
    assert counting_app("on", "youtube", MODE_PLAYING_ONLY, exceptions) is None
    assert (
        counting_app("playing", "youtube", MODE_PLAYING_ONLY, exceptions) == "youtube"
    )


def test_exceptions_flip_app_open_default() -> None:
    assert effective_mode("plex", MODE_APP_OPEN, {"plex"}) == MODE_PLAYING_ONLY
    assert counting_app("paused", "plex", MODE_APP_OPEN, {"plex"}) is None


def test_unknown_app_counts_only_while_playing() -> None:
    for default in (MODE_PLAYING_ONLY, MODE_APP_OPEN):
        assert effective_mode(UNKNOWN_APP_KEY, default, {UNKNOWN_APP_KEY}) == (
            MODE_PLAYING_ONLY
        )
    assert counting_app("on", UNKNOWN_APP_KEY, MODE_APP_OPEN, set()) is None
    assert counting_app("playing", UNKNOWN_APP_KEY, MODE_APP_OPEN, set()) == (
        UNKNOWN_APP_KEY
    )


def test_switching_between_sources_with_different_modes() -> None:
    exceptions = {"pc"}
    t = Tracker(grace_period=60)
    # PC (while open) for 10 min, then YouTube which is on but not yet playing.
    t.update(counting_app("on", "pc", MODE_PLAYING_ONLY, exceptions), 0)
    credits = t.update(
        counting_app("on", "youtube", MODE_PLAYING_ONLY, exceptions), 600
    )
    assert credits == []  # PC enters grace; YouTube isn't counting yet
    credits = t.update(
        counting_app("playing", "youtube", MODE_PLAYING_ONLY, exceptions), 620
    )
    assert credits == [("pc", 10.0)]
    assert t.state == Counting("youtube", 620)


def test_extra_entity_playing_counts_as_playing() -> None:
    # Observed on a Chromecast with Google TV: the Android TV Remote player
    # says "on", the Cast entity says "playing" for the same app.
    assert combined_player_state("on", "playing", "youtube", "youtube") == "playing"
    assert combined_player_state("on", "playing", None, "youtube") == "playing"
    assert combined_player_state("playing", "off", None, "youtube") == "playing"
    assert combined_player_state("on", "paused", "youtube", "youtube") == "on"
    assert combined_player_state("on", None, None, "youtube") == "on"


def test_extra_entity_playing_for_another_app_is_ignored() -> None:
    # Observed: a phone kept an F1 TV cast session open while Disney+ was on
    # screen; the Cast entity kept reporting F1 TV.
    assert combined_player_state("on", "playing", "f1tv_chromecast", "disney") == "on"


def test_main_player_decides_off() -> None:
    assert combined_player_state("off", "playing", None, None) == "off"
    assert combined_player_state("unavailable", "playing", None, None) == (
        "unavailable"
    )
    assert combined_player_state(None, "playing", None, None) is None
