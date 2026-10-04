"""Watch session state machine. No Home Assistant imports; time is passed in."""

from collections.abc import Collection
from dataclasses import dataclass

from .const import (
    INACTIVE_STATES,
    MODE_APP_OPEN,
    MODE_PLAYING_ONLY,
    STATE_PLAYING,
    UNKNOWN_APP_KEY,
)

type Credit = tuple[str, float]
"""(source_key, minutes)"""


@dataclass(frozen=True)
class Idle:
    """Nothing is being counted."""


@dataclass(frozen=True)
class Counting:
    """`app` has been counted since `since`."""

    app: str
    since: float


@dataclass(frozen=True)
class Grace:
    """`app` stopped counting at `gap_start`; it may resume within the grace period."""

    app: str
    since: float
    gap_start: float


type TrackerState = Idle | Counting | Grace


def effective_mode(app_key: str, default_mode: str, exceptions: Collection[str]) -> str:
    """Return the counting mode for an app on one device."""
    if app_key == UNKNOWN_APP_KEY:
        # Without a known app (e.g. a home screen), only playback shows watching.
        return MODE_PLAYING_ONLY
    if app_key not in exceptions:
        return default_mode
    return MODE_APP_OPEN if default_mode == MODE_PLAYING_ONLY else MODE_PLAYING_ONLY


def combined_player_state(
    player_state: str | None,
    extra_state: str | None,
    extra_app: str | None,
    app: str | None,
) -> str | None:
    """The media player decides on/off; either entity can say it is playing.

    E.g. a Chromecast with Google TV: the Android TV Remote player knows on/off
    and the app but never says "playing"; its Google Cast entity does.
    The extra entity's "playing" only counts when it names no app or the same
    app (`extra_app` == `app`, both source keys): a cast session left open on a
    phone keeps reporting its own app while another app is on screen.
    """
    if player_state is None or player_state in INACTIVE_STATES:
        return player_state
    if extra_state == STATE_PLAYING and extra_app in (None, app):
        return STATE_PLAYING
    return player_state


def counting_app(
    player_state: str | None,
    app_key: str | None,
    default_mode: str,
    exceptions: Collection[str],
) -> str | None:
    """Return the app being counted, or None for NotCounting.

    `player_state` is None when the media player doesn't exist.
    `app_key` is None when the app is ignored.
    """
    if app_key is None or player_state is None:
        return None
    if effective_mode(app_key, default_mode, exceptions) == MODE_PLAYING_ONLY:
        active = player_state == STATE_PLAYING
    else:
        active = player_state not in INACTIVE_STATES
    return app_key if active else None


def _credit(app: str, start: float, end: float) -> list[Credit]:
    if end <= start:
        return []
    return [(app, (end - start) / 60)]


class Tracker:
    """Turns a stream of situations into watch-time credits."""

    def __init__(self, grace_period: float) -> None:
        self.grace_period = grace_period
        self.state: TrackerState = Idle()

    def update(self, app: str | None, now: float) -> list[Credit]:
        """Feed the current situation: an app key (Counting) or None (NotCounting)."""
        state = self.state
        match state:
            case Idle():
                if app is not None:
                    self.state = Counting(app, now)
                return []
            case Counting():
                if app == state.app:
                    return []
                if app is None:
                    if self.grace_period <= 0:
                        self.state = Idle()
                        return _credit(state.app, state.since, now)
                    self.state = Grace(state.app, state.since, now)
                    return []
                self.state = Counting(app, now)
                return _credit(state.app, state.since, now)
            case Grace():
                if app is None:
                    return []
                if app == state.app:
                    self.state = Counting(app, state.since)
                    return []
                self.state = Counting(app, now)
                return _credit(state.app, state.since, state.gap_start)

    def tick(self, now: float) -> list[Credit]:
        """Credit the running session so far."""
        state = self.state
        if not isinstance(state, Counting):
            return []
        if now <= state.since:
            return []
        self.state = Counting(state.app, now)
        return _credit(state.app, state.since, now)

    def grace_expired(self) -> list[Credit]:
        """The grace period ran out without the app coming back."""
        state = self.state
        if not isinstance(state, Grace):
            return []
        self.state = Idle()
        return _credit(state.app, state.since, state.gap_start)

    def close(self, now: float) -> list[Credit]:
        """Shutdown/unload: close any open session."""
        state = self.state
        self.state = Idle()
        match state:
            case Counting():
                return _credit(state.app, state.since, now)
            case Grace():
                return _credit(state.app, state.since, state.gap_start)
        return []
