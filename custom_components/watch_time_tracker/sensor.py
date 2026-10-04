"""Watch time and activity sensors."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WatchTimeConfigEntry
from .const import COMBINED_DEVICE_ID, DOMAIN
from .device import TrackedDevice
from .hub import Hub
from .storage import Totals

COMBINED_DEVICE_NAME = "All TVs"

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WatchTimeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create sensors for known sources and add new ones as they appear."""
    runtime = entry.runtime_data
    hub = runtime.hub

    combined_info = DeviceInfo(
        identifiers={(DOMAIN, COMBINED_DEVICE_ID)},
        name=COMBINED_DEVICE_NAME,
        entry_type=DeviceEntryType.SERVICE,
    )

    @callback
    def add_combined(key: str) -> None:
        async_add_entities([CombinedWatchTimeSensor(hub, key, combined_info)])

    async_add_entities(
        CombinedWatchTimeSensor(hub, key, combined_info) for key in hub.totals
    )
    entry.async_on_unload(hub.add_new_source_listener(add_combined))

    for subentry_id, device in runtime.devices.items():
        info = DeviceInfo(
            identifiers={(DOMAIN, subentry_id)},
            name=device.name,
            entry_type=DeviceEntryType.SERVICE,
        )

        @callback
        def add_source(
            key: str, device: TrackedDevice = device, info: DeviceInfo = info
        ) -> None:
            async_add_entities(
                [DeviceWatchTimeSensor(device, key, info)],
                config_subentry_id=device.subentry_id,
            )

        async_add_entities(
            [
                ActivitySensor(device, info),
                *(DeviceWatchTimeSensor(device, key, info) for key in device.totals),
            ],
            config_subentry_id=subentry_id,
        )
        entry.async_on_unload(device.add_new_source_listener(add_source))


class _WatchTimeSensor(SensorEntity):
    """Running total in minutes, displayed in hours."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "watch_time"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_suggested_unit_of_measurement = UnitOfTime.HOURS
    _attr_suggested_display_precision = 1

    def __init__(self, totals: Totals, key: str, info: DeviceInfo) -> None:
        self._totals = totals
        self._key = key
        self._attr_device_info = info
        self._attr_translation_placeholders = {"app": totals[key]["display_name"]}

    @property
    def native_value(self) -> float:
        """Total minutes."""
        return self._totals[self._key]["minutes"]


class DeviceWatchTimeSensor(_WatchTimeSensor):
    """Watch time of one source on one TV."""

    def __init__(self, device: TrackedDevice, key: str, info: DeviceInfo) -> None:
        super().__init__(device.totals, key, info)
        self._device = device
        self._attr_unique_id = f"{device.subentry_id}_watch_{key}"

    async def async_added_to_hass(self) -> None:
        """Follow device updates."""
        self.async_on_remove(
            self._device.add_update_listener(self.async_write_ha_state)
        )


class CombinedWatchTimeSensor(_WatchTimeSensor):
    """Watch time of one source over all TVs."""

    def __init__(self, hub: Hub, key: str, info: DeviceInfo) -> None:
        super().__init__(hub.totals, key, info)
        self._hub = hub
        self._attr_unique_id = f"combined_watch_{key}"

    async def async_added_to_hass(self) -> None:
        """Follow hub updates."""
        self.async_on_remove(self._hub.add_update_listener(self.async_write_ha_state))


class ActivitySensor(SensorEntity):
    """What a TV is currently counting."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "activity"

    def __init__(self, device: TrackedDevice, info: DeviceInfo) -> None:
        self._device = device
        self._attr_device_info = info
        self._attr_unique_id = f"{device.subentry_id}_activity"

    @property
    def native_value(self) -> str:
        """App display name, `idle` or `off`."""
        return self._device.activity

    async def async_added_to_hass(self) -> None:
        """Follow device updates."""
        self.async_on_remove(
            self._device.add_update_listener(self.async_write_ha_state)
        )
