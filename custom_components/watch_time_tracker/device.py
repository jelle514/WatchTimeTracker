"""One tracked TV: watches entity states and feeds the tracker."""

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from time import monotonic
from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)

from .app_names import ResolvedApp, detect_app, resolve
from .const import (
    ACTIVITY_IDLE,
    ACTIVITY_OFF,
    CONF_DEFAULT_MODE,
    CONF_EXTRA_ENTITY,
    CONF_GRACE_PERIOD,
    CONF_MEDIA_PLAYER,
    CONF_MODE_EXCEPTIONS,
    INACTIVE_STATES,
    LIVE_TICK_SECONDS,
    UNKNOWN_APP_KEY,
    UNKNOWN_APP_NAME,
)
from .hub import Hub
from .storage import Totals, TotalsStore
from .tracker import (
    Counting,
    Credit,
    Grace,
    Tracker,
    combined_player_state,
    counting_app,
    effective_mode,
)

_UNKNOWN_APP = ResolvedApp(UNKNOWN_APP_KEY, UNKNOWN_APP_NAME)
_IGNORED_EXTRA_APP = "!ignored"  # never equals a source key ([a-z0-9_])


class TrackedDevice:
    """Tracks watch time for one sub-entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        hub: Hub,
        store: TotalsStore,
        subentry: ConfigSubentry,
        overrides: Mapping[str, str | None],
    ) -> None:
        self.hass = hass
        self.subentry_id = subentry.subentry_id
        self.name = subentry.title
        self._hub = hub
        self._store = store
        self._overrides = overrides
        data = subentry.data
        self.media_player: str = data[CONF_MEDIA_PLAYER]
        self.extra_entity: str | None = data.get(CONF_EXTRA_ENTITY)
        self.default_mode: str = data[CONF_DEFAULT_MODE]
        self.mode_exceptions: frozenset[str] = frozenset(
            data.get(CONF_MODE_EXCEPTIONS, [])
        )
        self.totals: Totals = store.device_totals(self.subentry_id)
        self._tracker = Tracker(float(data[CONF_GRACE_PERIOD]))
        self._names = {key: total["display_name"] for key, total in self.totals.items()}
        self.activity: str = ACTIVITY_OFF
        self.raw_app: str | None = None
        self.resolved_app: ResolvedApp | None = None
        self._last_source_list: tuple[str, ...] = ()
        self._unsub_state: CALLBACK_TYPE | None = None
        self._cancel_grace: CALLBACK_TYPE | None = None
        self._cancel_tick: CALLBACK_TYPE | None = None
        self._new_source_listeners: list[Callable[[str], None]] = []
        self._update_listeners: list[CALLBACK_TYPE] = []

    # Listeners (used by sensors)

    @callback
    def add_new_source_listener(self, listener: Callable[[str], None]) -> CALLBACK_TYPE:
        """Call `listener(key)` when this device gets a new source."""
        self._new_source_listeners.append(listener)
        return lambda: self._new_source_listeners.remove(listener)

    @callback
    def add_update_listener(self, listener: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Call `listener()` when totals or activity change."""
        self._update_listeners.append(listener)
        return lambda: self._update_listeners.remove(listener)

    # Lifecycle

    @callback
    def async_start(self) -> None:
        """Subscribe to entity changes and read the current situation."""
        entities = [self.media_player]
        if self.extra_entity:
            entities.append(self.extra_entity)
        self._unsub_state = async_track_state_change_event(
            self.hass, entities, self._handle_state_change
        )
        self._evaluate()

    @callback
    def async_stop(self) -> None:
        """Unsubscribe, cancel timers and credit any open session. Idempotent."""
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        self._apply(self._tracker.close(monotonic()))
        self._sync_timers()

    # Sources

    @callback
    def ensure_source(self, key: str, display_name: str) -> None:
        """Make sure a total (and sensor) exists for a source key."""
        self._names.setdefault(key, display_name)
        if key not in self.totals:
            self.totals[key] = {"display_name": display_name, "minutes": 0.0}
            self._store.schedule_save()
            for listener in list(self._new_source_listeners):
                listener(key)
        self._hub.ensure_source(key, display_name)

    def display_name(self, key: str) -> str:
        """Display name for a source key."""
        return self._names.get(key, key)

    # Internals

    @callback
    def _handle_state_change(self, event: Event[EventStateChangedData]) -> None:
        self._evaluate()

    @callback
    def _evaluate(self) -> None:
        player = self.hass.states.get(self.media_player)
        extra = self.hass.states.get(self.extra_entity) if self.extra_entity else None
        self._sync_source_list(player)

        self.raw_app, self.resolved_app = detect_app(
            player.attributes if player else {},
            extra.attributes if extra else None,
            self._overrides,
        )
        if self.raw_app is None:
            self.resolved_app = _UNKNOWN_APP
        extra_raw, extra_app = (
            detect_app({}, extra.attributes, self._overrides) if extra else (None, None)
        )
        if extra_app is not None:
            extra_key = extra_app.key
        elif extra_raw is not None:
            extra_key = _IGNORED_EXTRA_APP
        else:
            extra_key = None
        player_state = combined_player_state(
            player.state if player else None,
            extra.state if extra else None,
            extra_key,
            self.resolved_app.key if self.resolved_app else None,
        )
        app = counting_app(
            player_state,
            self.resolved_app.key if self.resolved_app else None,
            self.default_mode,
            self.mode_exceptions,
        )
        if app is not None and self.resolved_app is not None:
            self._names[app] = self.resolved_app.display_name
            self.ensure_source(app, self.resolved_app.display_name)

        self._apply(self._tracker.update(app, monotonic()))
        self._sync_timers()
        self._set_activity(player_state)

    @callback
    def _sync_source_list(self, player: State | None) -> None:
        source_list = (
            tuple(player.attributes.get("source_list") or ()) if player else ()
        )
        if source_list == self._last_source_list:
            return
        self._last_source_list = source_list
        for raw in source_list:
            if isinstance(raw, str) and (resolved := resolve(raw, self._overrides)):
                self.ensure_source(resolved.key, resolved.display_name)

    @callback
    def _apply(self, credits: list[Credit]) -> None:
        for key, minutes in credits:
            name = self.display_name(key)
            self.ensure_source(key, name)
            self.totals[key]["minutes"] += minutes
            self._hub.add_minutes(key, name, minutes)
        if credits:
            self._store.schedule_save()
            self._notify()

    @callback
    def _sync_timers(self) -> None:
        state = self._tracker.state
        if isinstance(state, Grace):
            if self._cancel_grace is None:
                self._cancel_grace = async_call_later(
                    self.hass, self._tracker.grace_period, self._grace_expired
                )
        elif self._cancel_grace is not None:
            self._cancel_grace()
            self._cancel_grace = None

        if isinstance(state, Counting):
            if self._cancel_tick is None:
                self._cancel_tick = async_track_time_interval(
                    self.hass, self._live_tick, timedelta(seconds=LIVE_TICK_SECONDS)
                )
        elif self._cancel_tick is not None:
            self._cancel_tick()
            self._cancel_tick = None

    @callback
    def _grace_expired(self, _now: datetime) -> None:
        self._cancel_grace = None
        self._apply(self._tracker.grace_expired())
        self._sync_timers()
        player = self.hass.states.get(self.media_player)
        self._set_activity(player.state if player else None)

    @callback
    def _live_tick(self, _now: datetime) -> None:
        self._apply(self._tracker.tick(monotonic()))

    @callback
    def _set_activity(self, player_state: str | None) -> None:
        state = self._tracker.state
        if isinstance(state, (Counting, Grace)):
            activity = self.display_name(state.app)
        elif player_state is None or player_state in INACTIVE_STATES:
            activity = ACTIVITY_OFF
        else:
            activity = ACTIVITY_IDLE
        if activity != self.activity:
            self.activity = activity
            self._notify()

    @callback
    def _notify(self) -> None:
        for listener in list(self._update_listeners):
            listener()

    def diagnostics(self) -> dict[str, Any]:
        """Diagnostics data for this device."""
        state = self._tracker.state
        current = self.resolved_app
        return {
            "name": self.name,
            "media_player": self.media_player,
            "extra_entity": self.extra_entity,
            "default_mode": self.default_mode,
            "mode_exceptions": sorted(self.mode_exceptions),
            "grace_period": self._tracker.grace_period,
            "tracker_state": type(state).__name__,
            "tracker_app": getattr(state, "app", None),
            "raw_app": self.raw_app,
            "resolved_app": (
                {"key": current.key, "display_name": current.display_name}
                if current
                else "ignored"
            ),
            "effective_mode": (
                effective_mode(current.key, self.default_mode, self.mode_exceptions)
                if current
                else None
            ),
            "activity": self.activity,
            "totals": self.totals,
        }
