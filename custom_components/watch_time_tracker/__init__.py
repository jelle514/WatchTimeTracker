"""Watch Time Tracker: watch time per app per TV."""

from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant

from .app_names import OverrideError, parse_overrides
from .const import CONF_NAME_OVERRIDES, SUBENTRY_TYPE_DEVICE
from .device import TrackedDevice
from .hub import Hub
from .storage import TotalsStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


@dataclass
class RuntimeData:
    """Objects living for as long as the entry is loaded."""

    store: TotalsStore
    hub: Hub
    devices: dict[str, TrackedDevice]


type WatchTimeConfigEntry = ConfigEntry[RuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: WatchTimeConfigEntry) -> bool:
    """Set up Watch Time Tracker from a config entry."""
    store = TotalsStore(hass)
    await store.async_load()

    # Drop totals of removed sub-entries; combined totals are kept.
    for subentry_id in store.device_ids():
        if subentry_id not in entry.subentries:
            store.remove_device(subentry_id)

    try:
        overrides = parse_overrides(entry.options.get(CONF_NAME_OVERRIDES, ""))
    except OverrideError as err:
        _LOGGER.error("Ignoring name overrides: %s", err)
        overrides = {}

    hub = Hub(store)
    devices = {
        subentry_id: TrackedDevice(hass, hub, store, subentry, overrides)
        for subentry_id, subentry in entry.subentries.items()
        if subentry.subentry_type == SUBENTRY_TYPE_DEVICE
    }
    entry.runtime_data = RuntimeData(store, hub, devices)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    for device in devices.values():
        device.async_start()

    async def _async_on_stop(_event: Event) -> None:
        await _async_close_sessions(entry.runtime_data)

    entry.async_on_unload(
        hass.bus.async_listen(EVENT_HOMEASSISTANT_STOP, _async_on_stop)
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WatchTimeConfigEntry) -> bool:
    """Close open sessions, save, and unload."""
    await _async_close_sessions(entry.runtime_data)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_close_sessions(runtime: RuntimeData) -> None:
    for device in runtime.devices.values():
        device.async_stop()
    await runtime.store.async_save()


async def _async_update_listener(
    hass: HomeAssistant, entry: WatchTimeConfigEntry
) -> None:
    """Reload on any sub-entry or options change."""
    await hass.config_entries.async_reload(entry.entry_id)
