"""Config, options and sub-entry flows for Watch Time Tracker."""

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)
import voluptuous as vol

from .app_names import OverrideError, parse_overrides, resolve
from .const import (
    CONF_DEFAULT_MODE,
    CONF_EXTRA_ENTITY,
    CONF_GRACE_PERIOD,
    CONF_MEDIA_PLAYER,
    CONF_MODE_EXCEPTIONS,
    CONF_NAME,
    CONF_NAME_OVERRIDES,
    DEFAULT_GRACE_PERIOD,
    DOMAIN,
    FIELD_COUNT_ONLY_WHILE_PLAYING,
    FIELD_COUNT_WHILE_OPEN,
    MAX_GRACE_PERIOD,
    MODE_PLAYING_ONLY,
    MODES,
    SUBENTRY_TYPE_DEVICE,
    UNKNOWN_APP_KEY,
)

TITLE = "Watch Time Tracker"


class WatchTimeTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create the single main entry."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """No fields; just create the entry."""
        if user_input is not None:
            return self.async_create_entry(title=TITLE, data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Name overrides."""
        return WatchTimeTrackerOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """One sub-entry type: a tracked TV."""
        return {SUBENTRY_TYPE_DEVICE: TrackedDeviceSubentryFlow}


class WatchTimeTrackerOptionsFlow(OptionsFlow):
    """Edit the app name overrides."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Multi-line overrides; invalid lines are named in the error."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            text = user_input.get(CONF_NAME_OVERRIDES, "")
            try:
                parse_overrides(text)
            except OverrideError as err:
                errors[CONF_NAME_OVERRIDES] = "invalid_override"
                placeholders = {"line_number": str(err.line_number), "line": err.line}
            else:
                return self.async_create_entry(data={CONF_NAME_OVERRIDES: text})

        current = (user_input or self.config_entry.options).get(CONF_NAME_OVERRIDES, "")
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_NAME_OVERRIDES, description={"suggested_value": current}
                ): TextSelector(TextSelectorConfig(multiline=True)),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders=placeholders,
        )


class TrackedDeviceSubentryFlow(ConfigSubentryFlow):
    """Add or reconfigure a tracked TV in two steps: device, then sources."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._exceptions_cleared = False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Step 1 when adding."""
        return await self._async_step_device("user", user_input, {})

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Step 1 when reconfiguring."""
        subentry = self._get_reconfigure_subentry()
        current = {CONF_NAME: subentry.title, **subentry.data}
        return await self._async_step_device("reconfigure", user_input, current)

    async def _async_step_device(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
        current: dict[str, Any],
    ) -> SubentryFlowResult:
        if user_input is not None:
            media_player = user_input[CONF_MEDIA_PLAYER]
            if self._media_player_taken(media_player):
                return self.async_abort(reason="already_tracked")
            name = (user_input.get(CONF_NAME) or "").strip()
            if not name:
                state = self.hass.states.get(media_player)
                name = state.name if state else media_player
            mode_exceptions = current.get(CONF_MODE_EXCEPTIONS, [])
            if self.source == "reconfigure" and user_input[
                CONF_DEFAULT_MODE
            ] != current.get(CONF_DEFAULT_MODE):
                # The old entries would now mean the opposite.
                mode_exceptions = []
                self._exceptions_cleared = True
            self._data = {
                CONF_NAME: name,
                CONF_MEDIA_PLAYER: media_player,
                CONF_EXTRA_ENTITY: user_input.get(CONF_EXTRA_ENTITY),
                CONF_DEFAULT_MODE: user_input[CONF_DEFAULT_MODE],
                CONF_GRACE_PERIOD: int(user_input[CONF_GRACE_PERIOD]),
                CONF_MODE_EXCEPTIONS: mode_exceptions,
            }
            return await self.async_step_sources()

        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME): str,
                vol.Required(CONF_MEDIA_PLAYER): EntitySelector(
                    EntitySelectorConfig(domain="media_player")
                ),
                vol.Optional(CONF_EXTRA_ENTITY): EntitySelector(
                    EntitySelectorConfig(domain=["remote", "media_player"])
                ),
                vol.Required(
                    CONF_DEFAULT_MODE, default=MODE_PLAYING_ONLY
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=list(MODES),
                        translation_key=CONF_DEFAULT_MODE,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required(
                    CONF_GRACE_PERIOD, default=DEFAULT_GRACE_PERIOD
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=MAX_GRACE_PERIOD,
                        step=1,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(schema, current),
        )

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Step 2: the sources that use the other counting mode."""
        field = (
            FIELD_COUNT_WHILE_OPEN
            if self._data[CONF_DEFAULT_MODE] == MODE_PLAYING_ONLY
            else FIELD_COUNT_ONLY_WHILE_PLAYING
        )
        overrides = self._overrides()

        if user_input is not None:
            keys: set[str] = set()
            offered = {option["value"] for option in self._source_options(overrides)}
            for value in user_input.get(field, []):
                if value in offered:
                    keys.add(value)
                elif resolved := resolve(value, overrides):
                    keys.add(resolved.key)
            keys.discard(UNKNOWN_APP_KEY)
            self._data[CONF_MODE_EXCEPTIONS] = sorted(keys)
            return self._async_finish()

        options = self._source_options(overrides)
        schema = vol.Schema(
            {
                vol.Optional(
                    field, default=list(self._data[CONF_MODE_EXCEPTIONS])
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        custom_value=True,
                        sort=True,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="sources_cleared" if self._exceptions_cleared else "sources",
            data_schema=schema,
        )

    async def async_step_sources_cleared(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Same as the sources step, with a notice that the list was cleared."""
        return await self.async_step_sources(user_input)

    def _async_finish(self) -> SubentryFlowResult:
        title = self._data.pop(CONF_NAME)
        if self.source == "reconfigure":
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                title=title,
                data=self._data,
            )
        return self.async_create_entry(title=title, data=self._data)

    def _media_player_taken(self, media_player: str) -> bool:
        own_id = (
            self._get_reconfigure_subentry().subentry_id
            if self.source == "reconfigure"
            else None
        )
        return any(
            subentry.data.get(CONF_MEDIA_PLAYER) == media_player
            for subentry_id, subentry in self._get_entry().subentries.items()
            if subentry_id != own_id
        )

    def _overrides(self) -> dict[str, str | None]:
        try:
            return parse_overrides(
                self._get_entry().options.get(CONF_NAME_OVERRIDES, "")
            )
        except OverrideError:
            return {}

    def _source_options(
        self, overrides: dict[str, str | None]
    ) -> list[SelectOptionDict]:
        """Source list of the media player + stored sources + current selection."""
        names: dict[str, str] = {}
        state = self.hass.states.get(self._data[CONF_MEDIA_PLAYER])
        for raw in (state.attributes.get("source_list") or []) if state else []:
            if isinstance(raw, str) and (resolved := resolve(raw, overrides)):
                names.setdefault(resolved.key, resolved.display_name)
        if self.source == "reconfigure":
            runtime = getattr(self._get_entry(), "runtime_data", None)
            subentry_id = self._get_reconfigure_subentry().subentry_id
            if runtime is not None and subentry_id in runtime.devices:
                for key, total in runtime.devices[subentry_id].totals.items():
                    names.setdefault(key, total["display_name"])
        for key in self._data[CONF_MODE_EXCEPTIONS]:
            names.setdefault(key, key)
        return [SelectOptionDict(value=key, label=name) for key, name in names.items()]
