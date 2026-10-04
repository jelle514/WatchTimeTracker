"""Tests for diagnostics."""

from homeassistant.core import HomeAssistant

from custom_components.watch_time_tracker.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import (
    LG,
    LG_SUBENTRY,
    FakeClock,
    device_subentry,
    make_entry,
    set_lg,
    setup,
)


async def test_diagnostics(hass: HomeAssistant, clock: FakeClock) -> None:
    set_lg(hass, "on", "PC")
    entry = await setup(
        hass, make_entry(device_subentry(LG_SUBENTRY, "LG", LG, mode_exceptions=["pc"]))
    )
    await clock.advance(60)

    diag = await async_get_config_entry_diagnostics(hass, entry)

    lg = diag["devices"][LG_SUBENTRY]
    assert lg["tracker_state"] == "Counting"
    assert lg["raw_app"] == "PC"
    assert lg["resolved_app"] == {"key": "pc", "display_name": "PC"}
    assert lg["default_mode"] == "playing_only"
    assert lg["mode_exceptions"] == ["pc"]
    assert lg["effective_mode"] == "app_open"
    assert lg["grace_period"] == 60
    assert lg["totals"]["pc"]["minutes"] > 0
    assert diag["combined"]["pc"]["minutes"] > 0
