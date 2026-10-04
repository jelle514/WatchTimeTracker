"""Persistent watch-time totals."""

from typing import Any, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, SAVE_DELAY_SECONDS

STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1
STORAGE_MINOR_VERSION = 1


class SourceTotal(TypedDict):
    """Stored total for one source."""

    display_name: str
    minutes: float


type Totals = dict[str, SourceTotal]
"""source_key -> total"""


class StoredData(TypedDict):
    """Layout of the storage file."""

    devices: dict[str, Totals]
    combined: Totals


class _TotalsStore(Store[StoredData]):
    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict[str, Any]
    ) -> StoredData:
        # Version 1.1 is the first version. Future migrations go here.
        if old_major_version > STORAGE_VERSION:
            raise NotImplementedError
        return old_data  # type: ignore[return-value]


class TotalsStore:
    """Loads and saves totals; the single source of truth."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store = _TotalsStore(
            hass, STORAGE_VERSION, STORAGE_KEY, minor_version=STORAGE_MINOR_VERSION
        )
        self._data: StoredData = {"devices": {}, "combined": {}}

    async def async_load(self) -> None:
        """Load from disk. Missing file gives empty totals."""
        if (data := await self._store.async_load()) is not None:
            self._data = {
                "devices": data.get("devices", {}),
                "combined": data.get("combined", {}),
            }

    @property
    def combined(self) -> Totals:
        """Combined totals (mutable, saved by schedule_save)."""
        return self._data["combined"]

    def device_totals(self, subentry_id: str) -> Totals:
        """Totals of one tracked device (created if missing)."""
        return self._data["devices"].setdefault(subentry_id, {})

    def device_ids(self) -> list[str]:
        """Sub-entry IDs that have stored totals."""
        return list(self._data["devices"])

    def remove_device(self, subentry_id: str) -> None:
        """Delete a device's totals. Combined totals are kept."""
        if self._data["devices"].pop(subentry_id, None) is not None:
            self.schedule_save()

    def schedule_save(self) -> None:
        """Save within SAVE_DELAY_SECONDS."""
        self._store.async_delay_save(lambda: self._data, SAVE_DELAY_SECONDS)

    async def async_save(self) -> None:
        """Save now."""
        await self._store.async_save(self._data)
