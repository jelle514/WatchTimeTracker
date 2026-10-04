"""Shared fixtures."""

from collections.abc import Generator
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigSubentryDataWithId
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.watch_time_tracker.const import (
    CONF_DEFAULT_MODE,
    CONF_EXTRA_ENTITY,
    CONF_GRACE_PERIOD,
    CONF_MEDIA_PLAYER,
    CONF_MODE_EXCEPTIONS,
    DOMAIN,
    MODE_PLAYING_ONLY,
    SUBENTRY_TYPE_DEVICE,
)

LG = "media_player.lg_webos_smart_tv"
LG_SUBENTRY = "lg_subentry"
CAST = "media_player.chromecast"
CAST_REMOTE = "remote.slaapkamer_tv"
CAST_SUBENTRY = "cast_subentry"

LG_SOURCES = ["YouTube", "Netflix", "PC", "Nintendo Switch Game Console"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let HA load custom_components/ in every test."""


class FakeClock:
    """Moves wall time (timers) and the integration's monotonic clock together."""

    def __init__(self, hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
        self.hass = hass
        self.freezer = freezer
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    async def advance(self, seconds: float) -> None:
        self.now += seconds
        self.freezer.tick(timedelta(seconds=seconds))
        async_fire_time_changed(self.hass)
        await self.hass.async_block_till_done()


@pytest.fixture
def clock(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> Generator[FakeClock]:
    """Fake clock patched into device.py."""
    fake = FakeClock(hass, freezer)
    with patch("custom_components.watch_time_tracker.device.monotonic", fake.monotonic):
        yield fake


def device_subentry(
    subentry_id: str,
    title: str,
    media_player: str,
    *,
    extra_entity: str | None = None,
    default_mode: str = MODE_PLAYING_ONLY,
    grace_period: int = 60,
    mode_exceptions: list[str] | None = None,
) -> ConfigSubentryDataWithId:
    """Sub-entry data for a tracked TV."""
    return ConfigSubentryDataWithId(
        subentry_id=subentry_id,
        subentry_type=SUBENTRY_TYPE_DEVICE,
        title=title,
        unique_id=None,
        data={
            CONF_MEDIA_PLAYER: media_player,
            CONF_EXTRA_ENTITY: extra_entity,
            CONF_DEFAULT_MODE: default_mode,
            CONF_GRACE_PERIOD: grace_period,
            CONF_MODE_EXCEPTIONS: mode_exceptions or [],
        },
    )


def make_entry(
    *subentries: ConfigSubentryDataWithId, options: dict[str, Any] | None = None
) -> MockConfigEntry:
    """Main entry with the given tracked TVs."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Watch Time Tracker",
        data={},
        options=options or {},
        subentries_data=list(subentries),
    )


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> MockConfigEntry:
    """Add and set up an entry."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def set_lg(hass: HomeAssistant, state: str, source: str | None = None) -> None:
    """Set the LG media player state."""
    attributes: dict[str, Any] = {"source_list": LG_SOURCES, "friendly_name": "LG"}
    if source is not None:
        attributes["source"] = source
    hass.states.async_set(LG, state, attributes)
