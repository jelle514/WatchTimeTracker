"""Constants for Watch Time Tracker."""

from typing import Final

DOMAIN: Final = "watch_time_tracker"

SUBENTRY_TYPE_DEVICE: Final = "device"

# Main entry options
CONF_NAME_OVERRIDES: Final = "name_overrides"

# Sub-entry data
CONF_NAME: Final = "name"
CONF_MEDIA_PLAYER: Final = "media_player"
CONF_EXTRA_ENTITY: Final = "extra_entity"
CONF_DEFAULT_MODE: Final = "default_mode"
CONF_GRACE_PERIOD: Final = "grace_period"
CONF_MODE_EXCEPTIONS: Final = "mode_exceptions"

# Form-only fields of the "sources" step. Two keys so the label can follow
# the default mode; both are stored as CONF_MODE_EXCEPTIONS.
FIELD_COUNT_WHILE_OPEN: Final = "count_while_open"
FIELD_COUNT_ONLY_WHILE_PLAYING: Final = "count_only_while_playing"

MODE_PLAYING_ONLY: Final = "playing_only"
MODE_APP_OPEN: Final = "app_open"
MODES: Final = (MODE_PLAYING_ONLY, MODE_APP_OPEN)

DEFAULT_GRACE_PERIOD: Final = 60
MAX_GRACE_PERIOD: Final = 600

LIVE_TICK_SECONDS: Final = 60
SAVE_DELAY_SECONDS: Final = 30

UNKNOWN_APP_KEY: Final = "unknown_app"
UNKNOWN_APP_NAME: Final = "Unknown app"

# Media player states that never count, whatever the mode
INACTIVE_STATES: Final = frozenset({"off", "unavailable", "unknown", "standby"})
STATE_PLAYING: Final = "playing"

ACTIVITY_IDLE: Final = "idle"
ACTIVITY_OFF: Final = "off"

COMBINED_DEVICE_ID: Final = "combined"


def watch_unique_id(subentry_id: str | None, key: str) -> str:
    """Unique ID of a watch-time sensor; subentry_id None is the combined sensor."""
    if subentry_id is None:
        return f"combined_watch_{key}"
    return f"{subentry_id}_watch_{key}"


def total_unique_id(subentry_id: str | None) -> str:
    """Unique ID of an all-sources sensor; subentry_id None is the combined sensor.

    Doesn't match the watch_unique_id pattern, whatever the source key.
    """
    return f"{subentry_id or COMBINED_DEVICE_ID}_total_watch"
