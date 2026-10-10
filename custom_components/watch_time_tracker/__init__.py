"""Watch Time Tracker: watch time per app per TV."""

from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import entity_registry as er

from .app_names import OverrideError, parse_overrides, renamed_keys, resolve
from .const import (
    CONF_MODE_EXCEPTIONS,
    CONF_NAME_OVERRIDES,
    DOMAIN,
    SUBENTRY_TYPE_DEVICE,
    watch_unique_id,
)
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

    overrides_text = entry.options.get(CONF_NAME_OVERRIDES, "")
    try:
        overrides = parse_overrides(overrides_text)
    except OverrideError as err:
        _LOGGER.error("Ignoring name overrides: %s", err)
        overrides = {}
    else:
        _async_carry_over_renames(hass, entry, store, overrides)
        store.name_overrides = overrides_text

    # Drop sources the name mapping now ignores, if they never counted any time,
    # so their sensors don't come back at every startup.
    ent_reg = er.async_get(hass)
    for subentry_id, key in store.prune_unused(
        lambda name: resolve(name, overrides) is None
    ):
        unique_id = watch_unique_id(subentry_id, key)
        if entity_id := ent_reg.async_get_entity_id(Platform.SENSOR, DOMAIN, unique_id):
            ent_reg.async_remove(entity_id)

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


def _async_carry_over_renames(
    hass: HomeAssistant,
    entry: WatchTimeConfigEntry,
    store: TotalsStore,
    overrides: dict[str, str | None],
) -> None:
    """Move totals, sensors and counting modes of renamed sources to their new key.

    Compares with the overrides the totals were last keyed with. Without a
    record (totals from before 0.1.3), compares with no overrides at all.
    Runs before the update listener is added, so updating sub-entries here
    doesn't reload the entry.
    """
    try:
        previous = parse_overrides(store.name_overrides or "")
    except OverrideError:
        previous = {}
    renames = {
        old_key: (app.key, app.display_name)
        for old_key, app in renamed_keys(previous, overrides).items()
    }
    if not renames:
        return

    ent_reg = er.async_get(hass)
    for subentry_id, old_key, new_key in store.rename_sources(renames):
        _LOGGER.info("Moved watch time of %s to %s", old_key, new_key)
        old_id = ent_reg.async_get_entity_id(
            Platform.SENSOR, DOMAIN, watch_unique_id(subentry_id, old_key)
        )
        if old_id is None:
            continue
        new_unique_id = watch_unique_id(subentry_id, new_key)
        if ent_reg.async_get_entity_id(Platform.SENSOR, DOMAIN, new_unique_id):
            ent_reg.async_remove(old_id)
        else:
            # Keep the entity (and its history); only its unique ID follows the key.
            ent_reg.async_update_entity(old_id, new_unique_id=new_unique_id)

    for subentry in entry.subentries.values():
        exceptions = subentry.data.get(CONF_MODE_EXCEPTIONS, [])
        updated = sorted({renames.get(key, (key,))[0] for key in exceptions})
        if updated != sorted(exceptions):
            hass.config_entries.async_update_subentry(
                entry, subentry, data={**subentry.data, CONF_MODE_EXCEPTIONS: updated}
            )


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
