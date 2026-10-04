"""Diagnostics for Watch Time Tracker."""

from typing import Any

from homeassistant.core import HomeAssistant

from . import WatchTimeConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: WatchTimeConfigEntry
) -> dict[str, Any]:
    """Return tracker state, app detection and totals per device."""
    runtime = entry.runtime_data
    return {
        "options": dict(entry.options),
        "devices": {
            subentry_id: device.diagnostics()
            for subentry_id, device in runtime.devices.items()
        },
        "combined": runtime.hub.totals,
    }
