"""Tests for the main flow, options flow and tracked-TV sub-entry flow."""

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.watch_time_tracker.const import (
    CONF_DEFAULT_MODE,
    CONF_EXTRA_ENTITY,
    CONF_GRACE_PERIOD,
    CONF_MEDIA_PLAYER,
    CONF_MODE_EXCEPTIONS,
    CONF_NAME,
    CONF_NAME_OVERRIDES,
    DOMAIN,
    FIELD_COUNT_ONLY_WHILE_PLAYING,
    FIELD_COUNT_WHILE_OPEN,
    MODE_APP_OPEN,
    MODE_PLAYING_ONLY,
    SUBENTRY_TYPE_DEVICE,
)

from .conftest import (
    CAST,
    LG,
    LG_SUBENTRY,
    device_subentry,
    make_entry,
    set_lg,
    setup,
)


async def test_main_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Watch Time Tracker"


async def test_main_flow_single_instance(hass: HomeAssistant) -> None:
    make_entry().add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow_valid(hass: HomeAssistant) -> None:
    entry = await setup(hass, make_entry())
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_NAME_OVERRIDES: "com.foo = Foo\nlauncher = !ignore"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_NAME_OVERRIDES] == "com.foo = Foo\nlauncher = !ignore"


async def test_options_flow_names_bad_line(hass: HomeAssistant) -> None:
    entry = await setup(hass, make_entry())
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_NAME_OVERRIDES: "ok = Fine\nbroken line"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_NAME_OVERRIDES: "invalid_override"}
    assert result["description_placeholders"] == {
        "line_number": "2",
        "line": "broken line",
    }


async def _start_subentry_flow(hass: HomeAssistant, entry_id: str):
    return await hass.config_entries.subentries.async_init(
        (entry_id, SUBENTRY_TYPE_DEVICE), context={"source": SOURCE_USER}
    )


async def test_add_tracked_tv(hass: HomeAssistant) -> None:
    set_lg(hass, "on")
    entry = await setup(hass, make_entry())

    result = await _start_subentry_flow(hass, entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_MEDIA_PLAYER: LG,
            CONF_DEFAULT_MODE: MODE_PLAYING_ONLY,
            CONF_GRACE_PERIOD: 60,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sources"
    # Label follows the default mode; options come from source_list.
    field = next(iter(result["data_schema"].schema))
    assert str(field) == FIELD_COUNT_WHILE_OPEN
    options = result["data_schema"].schema[field].config["options"]
    assert {"value": "pc", "label": "PC"} in options

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {FIELD_COUNT_WHILE_OPEN: ["pc", "Nintendo Switch Game Console"]},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    (subentry,) = entry.subentries.values()
    assert subentry.title == "LG"  # friendly name of the media player
    assert subentry.data[CONF_MEDIA_PLAYER] == LG
    assert subentry.data[CONF_MODE_EXCEPTIONS] == ["nintendo_switch_game_console", "pc"]
    # The update listener reloaded the entry; the new TV's sensors exist.
    assert hass.states.get("sensor.lg_activity") is not None


async def test_sources_label_for_app_open_default(hass: HomeAssistant) -> None:
    entry = await setup(hass, make_entry())
    result = await _start_subentry_flow(hass, entry.entry_id)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Slaapkamer",
            CONF_MEDIA_PLAYER: CAST,
            CONF_DEFAULT_MODE: MODE_APP_OPEN,
            CONF_GRACE_PERIOD: 30,
        },
    )
    field = next(iter(result["data_schema"].schema))
    assert str(field) == FIELD_COUNT_ONLY_WHILE_PLAYING
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {FIELD_COUNT_ONLY_WHILE_PLAYING: ["com.plexapp.android"]}
    )
    (subentry,) = entry.subentries.values()
    assert subentry.title == "Slaapkamer"
    # Custom values are resolved through the name mapping to a source key.
    assert subentry.data[CONF_MODE_EXCEPTIONS] == ["plex"]


async def test_duplicate_media_player_aborts(hass: HomeAssistant) -> None:
    entry = await setup(hass, make_entry(device_subentry(LG_SUBENTRY, "LG", LG)))
    result = await _start_subentry_flow(hass, entry.entry_id)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_MEDIA_PLAYER: LG,
            CONF_DEFAULT_MODE: MODE_PLAYING_ONLY,
            CONF_GRACE_PERIOD: 60,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_tracked"


async def _start_reconfigure(hass: HomeAssistant, entry_id: str, subentry_id: str):
    return await hass.config_entries.subentries.async_init(
        (entry_id, SUBENTRY_TYPE_DEVICE),
        context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry_id},
    )


async def test_reconfigure(hass: HomeAssistant) -> None:
    set_lg(hass, "on", "Plex")
    entry = await setup(
        hass, make_entry(device_subentry(LG_SUBENTRY, "LG", LG, mode_exceptions=["pc"]))
    )
    entry.runtime_data.devices[LG_SUBENTRY].ensure_source("plex", "Plex")

    result = await _start_reconfigure(hass, entry.entry_id, LG_SUBENTRY)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Woonkamer TV",
            CONF_MEDIA_PLAYER: LG,
            CONF_DEFAULT_MODE: MODE_PLAYING_ONLY,
            CONF_GRACE_PERIOD: 90,
        },
    )
    assert result["step_id"] == "sources"
    field = next(iter(result["data_schema"].schema))
    assert field.default() == ["pc"]  # current selection is kept
    options = result["data_schema"].schema[field].config["options"]
    assert {"value": "plex", "label": "Plex"} in options  # stored source

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {FIELD_COUNT_WHILE_OPEN: ["pc", "plex"]}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    subentry = entry.subentries[LG_SUBENTRY]
    assert subentry.title == "Woonkamer TV"
    assert subentry.data[CONF_GRACE_PERIOD] == 90
    assert subentry.data[CONF_MODE_EXCEPTIONS] == ["pc", "plex"]
    assert subentry.data[CONF_EXTRA_ENTITY] is None


async def test_reconfigure_to_taken_media_player_aborts(hass: HomeAssistant) -> None:
    entry = await setup(
        hass,
        make_entry(
            device_subentry(LG_SUBENTRY, "LG", LG),
            device_subentry("cast_subentry", "Cast", CAST),
        ),
    )
    result = await _start_reconfigure(hass, entry.entry_id, LG_SUBENTRY)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_MEDIA_PLAYER: CAST,
            CONF_DEFAULT_MODE: MODE_PLAYING_ONLY,
            CONF_GRACE_PERIOD: 60,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_tracked"


async def test_reconfigure_default_mode_change_clears_sources(
    hass: HomeAssistant,
) -> None:
    set_lg(hass, "on")
    entry = await setup(
        hass, make_entry(device_subentry(LG_SUBENTRY, "LG", LG, mode_exceptions=["pc"]))
    )
    result = await _start_reconfigure(hass, entry.entry_id, LG_SUBENTRY)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_MEDIA_PLAYER: LG,
            CONF_DEFAULT_MODE: MODE_APP_OPEN,
            CONF_GRACE_PERIOD: 60,
        },
    )
    assert result["step_id"] == "sources_cleared"
    field = next(iter(result["data_schema"].schema))
    assert str(field) == FIELD_COUNT_ONLY_WHILE_PLAYING
    assert field.default() == []

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {FIELD_COUNT_ONLY_WHILE_PLAYING: []}
    )
    assert result["type"] is FlowResultType.ABORT
    await hass.async_block_till_done()
    data = entry.subentries[LG_SUBENTRY].data
    assert data[CONF_MODE_EXCEPTIONS] == []
    assert data[CONF_DEFAULT_MODE] == MODE_APP_OPEN


async def _reconfigure_sources(hass: HomeAssistant, entry, selected: list[str]):
    result = await _start_reconfigure(hass, entry.entry_id, LG_SUBENTRY)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_MEDIA_PLAYER: LG,
            CONF_DEFAULT_MODE: MODE_PLAYING_ONLY,
            CONF_GRACE_PERIOD: 60,
        },
    )
    assert result["step_id"] == "sources"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {FIELD_COUNT_WHILE_OPEN: selected}
    )
    assert result["type"] is FlowResultType.ABORT
    await hass.async_block_till_done()
    return entry.subentries[LG_SUBENTRY].data[CONF_MODE_EXCEPTIONS]


async def test_sources_keep_offered_key_despite_override(hass: HomeAssistant) -> None:
    set_lg(hass, "on")
    entry = await setup(
        hass,
        make_entry(
            device_subentry(LG_SUBENTRY, "LG", LG, mode_exceptions=["pc"]),
            options={CONF_NAME_OVERRIDES: "PC = Gaming PC"},
        ),
    )
    entry.runtime_data.devices[LG_SUBENTRY].ensure_source("pc", "PC")
    assert await _reconfigure_sources(hass, entry, ["pc"]) == ["pc"]


async def test_sources_drop_unknown_app(hass: HomeAssistant) -> None:
    set_lg(hass, "on")
    entry = await setup(hass, make_entry(device_subentry(LG_SUBENTRY, "LG", LG)))
    stored = await _reconfigure_sources(hass, entry, ["Unknown app", "pc"])
    assert stored == ["pc"]


async def test_reconfigure_to_other_media_player_keeps_totals(
    hass: HomeAssistant,
) -> None:
    set_lg(hass, "on")
    hass.states.async_set("media_player.other_tv", "on", {"friendly_name": "Other"})
    entry = await setup(hass, make_entry(device_subentry(LG_SUBENTRY, "LG", LG)))
    device = entry.runtime_data.devices[LG_SUBENTRY]
    device.ensure_source("plex", "Plex")
    device.totals["plex"]["minutes"] = 12.5

    result = await _start_reconfigure(hass, entry.entry_id, LG_SUBENTRY)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_MEDIA_PLAYER: "media_player.other_tv",
            CONF_DEFAULT_MODE: MODE_PLAYING_ONLY,
            CONF_GRACE_PERIOD: 60,
        },
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {FIELD_COUNT_WHILE_OPEN: []}
    )
    assert result["type"] is FlowResultType.ABORT
    await hass.async_block_till_done()

    assert entry.subentries[LG_SUBENTRY].data[CONF_MEDIA_PLAYER] == (
        "media_player.other_tv"
    )
    totals = entry.runtime_data.devices[LG_SUBENTRY].totals
    assert totals["plex"] == {"display_name": "Plex", "minutes": 12.5}
