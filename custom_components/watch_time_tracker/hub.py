"""Combined totals across all tracked devices."""

from collections.abc import Callable

from homeassistant.core import CALLBACK_TYPE, callback

from .storage import Totals, TotalsStore


class Hub:
    """Owns the combined totals and tells sensors about changes."""

    def __init__(self, store: TotalsStore) -> None:
        self._store = store
        self._new_source_listeners: list[Callable[[str], None]] = []
        self._update_listeners: list[CALLBACK_TYPE] = []

    @property
    def totals(self) -> Totals:
        """Combined totals by source key."""
        return self._store.combined

    @callback
    def ensure_source(self, key: str, display_name: str) -> None:
        """Make sure a combined total (and sensor) exists for a source key."""
        if key in self.totals:
            return
        self.totals[key] = {"display_name": display_name, "minutes": 0.0}
        self._store.schedule_save()
        for listener in list(self._new_source_listeners):
            listener(key)

    @callback
    def add_minutes(self, key: str, display_name: str, minutes: float) -> None:
        """Add a device's credit to the combined total."""
        self.ensure_source(key, display_name)
        self.totals[key]["minutes"] += minutes
        self._store.schedule_save()
        for listener in list(self._update_listeners):
            listener()

    @callback
    def add_new_source_listener(self, listener: Callable[[str], None]) -> CALLBACK_TYPE:
        """Call `listener(key)` when a combined source is created."""
        self._new_source_listeners.append(listener)
        return lambda: self._new_source_listeners.remove(listener)

    @callback
    def add_update_listener(self, listener: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Call `listener()` when combined totals change."""
        self._update_listeners.append(listener)
        return lambda: self._update_listeners.remove(listener)
