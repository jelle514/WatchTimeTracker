"""Config flow for Watch Time Tracker."""

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN

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
