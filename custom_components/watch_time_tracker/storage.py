"""Persistent watch-time totals."""

from collections.abc import Callable, Mapping
from typing import Any, NotRequired, TypedDict

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
    name_overrides: NotRequired[str]
    """Override text the totals were last keyed with."""


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
            if (overrides := data.get("name_overrides")) is not None:
                self._data["name_overrides"] = overrides

    @property
    def name_overrides(self) -> str | None:
        """Override text the totals were last keyed with; None if not recorded."""
        return self._data.get("name_overrides")

    @name_overrides.setter
    def name_overrides(self, text: str) -> None:
        if self._data.get("name_overrides") != text:
            self._data["name_overrides"] = text
            self.schedule_save()

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

    def prune_unused(
        self, is_ignored: Callable[[str], bool]
    ) -> list[tuple[str | None, str]]:
        """Delete totals without recorded time whose source is now ignored.

        Returns (subentry_id, key) per deleted total; subentry_id is None for a
        combined total. Totals with recorded time are always kept.
        """
        removed: list[tuple[str | None, str]] = []
        for subentry_id, totals in self._scopes():
            for key in [
                key
                for key, total in totals.items()
                if total["minutes"] <= 0 and is_ignored(total["display_name"])
            ]:
                del totals[key]
                removed.append((subentry_id, key))
        if removed:
            self.schedule_save()
        return removed

    def rename_sources(
        self, renames: Mapping[str, tuple[str, str]]
    ) -> list[tuple[str | None, str, str]]:
        """Move totals from old keys to new (key, display name) pairs.

        Minutes are added to an existing total under the new key. Returns
        (subentry_id, old key, new key) per moved total; subentry_id is None for
        a combined total.
        """
        moved: list[tuple[str | None, str, str]] = []
        for subentry_id, totals in self._scopes():
            for old_key, (new_key, display_name) in renames.items():
                if (total := totals.pop(old_key, None)) is None:
                    continue
                target = totals.setdefault(
                    new_key, {"display_name": display_name, "minutes": 0.0}
                )
                target["display_name"] = display_name
                target["minutes"] += total["minutes"]
                moved.append((subentry_id, old_key, new_key))
        if moved:
            self.schedule_save()
        return moved

    def _scopes(self) -> list[tuple[str | None, Totals]]:
        return [*self._data["devices"].items(), (None, self._data["combined"])]

    def schedule_save(self) -> None:
        """Save within SAVE_DELAY_SECONDS."""
        self._store.async_delay_save(lambda: self._data, SAVE_DELAY_SECONDS)

    async def async_save(self) -> None:
        """Save now."""
        await self._store.async_save(self._data)
