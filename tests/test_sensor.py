"""End-to-end tracking: entity states in, sensor states out."""

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest

from custom_components.watch_time_tracker.const import (
    CONF_NAME_OVERRIDES,
    DOMAIN,
    MODE_APP_OPEN,
)
from custom_components.watch_time_tracker.storage import STORAGE_KEY

from .conftest import (
    CAST,
    CAST_REMOTE,
    CAST_SUBENTRY,
    LG,
    LG_SOURCES,
    LG_SUBENTRY,
    FakeClock,
    device_subentry,
    make_entry,
    set_lg,
    setup,
)

LG_YOUTUBE = "sensor.lg_youtube_watch_time"
LG_PC = "sensor.lg_pc_watch_time"
LG_ACTIVITY = "sensor.lg_activity"
LG_CAST = "media_player.lg_webos_tv_oled55c34la_2"  # built-in Chromecast
SLAAPKAMER_ATV = "media_player.slaapkamer_tv_2"  # Android TV Remote player
ALL_YOUTUBE = "sensor.all_tvs_youtube_watch_time"


def minutes(hass: HomeAssistant, entity_id: str) -> float:
    """Sensor state converted back to minutes (sensors display in hours)."""
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    assert state.attributes["unit_of_measurement"] == "h"
    return float(state.state) * 60


def lg_entry(**kwargs):
    return make_entry(device_subentry(LG_SUBENTRY, "LG", LG, **kwargs))


async def test_sensors_created_from_source_list(
    hass: HomeAssistant, clock: FakeClock
) -> None:
    set_lg(hass, "on")
    entry = await setup(hass, lg_entry())

    ent_reg = er.async_get(hass)
    youtube = ent_reg.async_get(LG_YOUTUBE)
    assert youtube is not None
    assert youtube.unique_id == f"{LG_SUBENTRY}_watch_youtube"
    assert youtube.config_subentry_id == LG_SUBENTRY
    assert ent_reg.async_get(ALL_YOUTUBE).unique_id == "combined_watch_youtube"
    assert ent_reg.async_get("sensor.lg_nintendo_switch_game_console_watch_time")

    state = hass.states.get(LG_YOUTUBE)
    assert state.attributes["device_class"] == "duration"
    assert state.attributes["state_class"] == "total_increasing"
    assert float(state.state) == 0

    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, LG_SUBENTRY), entry.entry_id
    )
    assert device is not None
    assert device.config_subentry_id == LG_SUBENTRY
    assert entry.state.name == "LOADED"


async def test_playing_is_counted_with_live_ticks(
    hass: HomeAssistant, clock: FakeClock
) -> None:
    set_lg(hass, "on", "YouTube")
    await setup(hass, lg_entry())
    set_lg(hass, "playing", "YouTube")
    await hass.async_block_till_done()
    assert hass.states.get(LG_ACTIVITY).state == "YouTube"

    await clock.advance(60)
    await clock.advance(60)
    assert minutes(hass, LG_YOUTUBE) == pytest.approx(2.0, abs=0.1)
    assert minutes(hass, ALL_YOUTUBE) == pytest.approx(2.0, abs=0.1)


async def test_short_gap_counts_long_gap_does_not(
    hass: HomeAssistant, clock: FakeClock
) -> None:
    set_lg(hass, "playing", "YouTube")
    await setup(hass, lg_entry())

    await clock.advance(30)
    set_lg(hass, "paused", "YouTube")  # between two videos
    await hass.async_block_till_done()
    await clock.advance(10)
    set_lg(hass, "playing", "YouTube")
    await hass.async_block_till_done()
    await clock.advance(20)
    set_lg(hass, "paused", "YouTube")  # user stops watching
    await hass.async_block_till_done()
    assert hass.states.get(LG_ACTIVITY).state == "YouTube"  # still in grace
    await clock.advance(61)

    # 30 + 10 (gap) + 20 = 60 s; the final 61 s gap is not counted.
    assert minutes(hass, LG_YOUTUBE) == pytest.approx(1.0, abs=0.1)
    assert hass.states.get(LG_ACTIVITY).state == "idle"


async def test_per_source_mode(hass: HomeAssistant, clock: FakeClock) -> None:
    set_lg(hass, "on", "PC")
    await setup(hass, lg_entry(mode_exceptions=["pc"]))
    await clock.advance(120)
    assert minutes(hass, LG_PC) == pytest.approx(2.0, abs=0.1)

    set_lg(hass, "on", "YouTube")  # YouTube open but not playing
    await hass.async_block_till_done()
    await clock.advance(120)
    assert minutes(hass, LG_YOUTUBE) == 0


async def test_ignored_app_is_not_counted(
    hass: HomeAssistant, clock: FakeClock
) -> None:
    hass.states.async_set(
        CAST, "idle", {"app_name": "com.google.android.apps.tv.launcherx"}
    )
    await setup(
        hass,
        make_entry(
            device_subentry(
                CAST_SUBENTRY, "Slaapkamer", CAST, default_mode=MODE_APP_OPEN
            )
        ),
    )
    await clock.advance(120)
    assert hass.states.get("sensor.slaapkamer_activity").state == "idle"
    assert not [s for s in hass.states.async_entity_ids("sensor") if "launcher" in s]


async def test_unknown_app_is_credited(hass: HomeAssistant, clock: FakeClock) -> None:
    hass.states.async_set(CAST, "playing", {})
    await setup(hass, make_entry(device_subentry(CAST_SUBENTRY, "Slaapkamer", CAST)))
    assert hass.states.get("sensor.slaapkamer_activity").state == "Unknown app"
    await clock.advance(60)
    assert minutes(hass, "sensor.slaapkamer_unknown_app_watch_time") == pytest.approx(
        1.0, abs=0.1
    )


async def test_home_screen_is_not_counted(
    hass: HomeAssistant, clock: FakeClock
) -> None:
    # Observed: on the home screen the LG reports "on" without a source.
    set_lg(hass, "on")
    await setup(hass, lg_entry(default_mode=MODE_APP_OPEN))
    await clock.advance(120)
    assert hass.states.get(LG_ACTIVITY).state == "idle"
    assert hass.states.get("sensor.lg_unknown_app_watch_time") is None


async def test_extra_entity_and_override(hass: HomeAssistant, clock: FakeClock) -> None:
    hass.states.async_set(CAST, "playing", {})
    hass.states.async_set(CAST_REMOTE, "on", {"current_activity": "com.netflix.ninja"})
    entry = make_entry(
        device_subentry(CAST_SUBENTRY, "Slaapkamer", CAST, extra_entity=CAST_REMOTE),
        options={CONF_NAME_OVERRIDES: "com.netflix.ninja = Netflix NL"},
    )
    await setup(hass, entry)
    await clock.advance(60)
    assert minutes(hass, "sensor.slaapkamer_netflix_nl_watch_time") == pytest.approx(
        1.0, abs=0.1
    )


async def test_casting_to_lg_uses_builtin_chromecast(
    hass: HomeAssistant, clock: FakeClock
) -> None:
    # Observed: while casting, the LG reports playing without a source,
    # and its built-in Chromecast reports the app.
    set_lg(hass, "playing")
    hass.states.async_set(
        LG_CAST, "playing", {"app_id": "B3E81094", "app_name": "F1TV Chromecast"}
    )
    await setup(hass, lg_entry(extra_entity=LG_CAST))
    assert hass.states.get(LG_ACTIVITY).state == "F1 TV"
    await clock.advance(60)
    assert minutes(hass, "sensor.lg_f1_tv_watch_time") == pytest.approx(1.0, abs=0.1)


async def test_google_tv_cast_entity_supplies_playing(
    hass: HomeAssistant, clock: FakeClock
) -> None:
    # Observed on the Slaapkamer TV: the Android TV Remote player says "on"
    # with the package name, its Google Cast entity says "playing".
    hass.states.async_set(
        SLAAPKAMER_ATV, "on", {"app_name": "com.google.android.youtube.tv"}
    )
    hass.states.async_set(CAST, "playing", {"app_name": "YouTube"})
    await setup(
        hass,
        make_entry(
            device_subentry(
                CAST_SUBENTRY, "Slaapkamer", SLAAPKAMER_ATV, extra_entity=CAST
            )
        ),
    )
    assert hass.states.get("sensor.slaapkamer_activity").state == "YouTube"
    await clock.advance(60)

    # Home screen: launcher (ignored) and no cast session.
    hass.states.async_set(
        SLAAPKAMER_ATV, "on", {"app_name": "com.google.android.apps.tv.launcherx"}
    )
    hass.states.async_set(CAST, "off", {})
    await hass.async_block_till_done()
    await clock.advance(120)

    assert hass.states.get("sensor.slaapkamer_activity").state == "idle"
    assert minutes(hass, "sensor.slaapkamer_youtube_watch_time") == pytest.approx(
        1.0, abs=0.1
    )


async def test_casting_app_without_google_tv_app(
    hass: HomeAssistant, clock: FakeClock
) -> None:
    # Observed: casting F1 TV to the Slaapkamer TV. The Android TV Remote player
    # reports the Cast receiver (ignored); the Cast entity names the app.
    hass.states.async_set(
        SLAAPKAMER_ATV, "on", {"app_name": "com.google.android.apps.mediashell"}
    )
    hass.states.async_set(CAST, "playing", {"app_name": "F1TV Chromecast"})
    await setup(
        hass,
        make_entry(
            device_subentry(
                CAST_SUBENTRY, "Slaapkamer", SLAAPKAMER_ATV, extra_entity=CAST
            )
        ),
    )
    assert hass.states.get("sensor.slaapkamer_activity").state == "F1 TV"
    await clock.advance(60)
    assert minutes(hass, "sensor.slaapkamer_f1_tv_watch_time") == pytest.approx(
        1.0, abs=0.1
    )


async def test_stale_cast_session_is_ignored(
    hass: HomeAssistant, clock: FakeClock
) -> None:
    # Observed: a phone kept an F1 TV cast session open while Disney+ was
    # opened on the Slaapkamer TV.
    hass.states.async_set(SLAAPKAMER_ATV, "on", {"app_name": "com.disney.disneyplus"})
    hass.states.async_set(CAST, "playing", {"app_name": "F1TV Chromecast"})
    await setup(
        hass,
        make_entry(
            device_subentry(
                CAST_SUBENTRY, "Slaapkamer", SLAAPKAMER_ATV, extra_entity=CAST
            )
        ),
    )
    await clock.advance(120)
    assert hass.states.get("sensor.slaapkamer_activity").state == "idle"
    assert hass.states.get("sensor.slaapkamer_disney_watch_time") is None


async def test_cast_session_for_ignored_app_is_ignored(
    hass: HomeAssistant, clock: FakeClock
) -> None:
    hass.states.async_set(SLAAPKAMER_ATV, "on", {"app_name": "com.disney.disneyplus"})
    hass.states.async_set(CAST, "playing", {"app_name": "Backdrop"})
    await setup(
        hass,
        make_entry(
            device_subentry(
                CAST_SUBENTRY, "Slaapkamer", SLAAPKAMER_ATV, extra_entity=CAST
            ),
            options={CONF_NAME_OVERRIDES: "Backdrop = !ignore"},
        ),
    )
    await clock.advance(120)
    assert hass.states.get("sensor.slaapkamer_activity").state == "idle"
    assert hass.states.get("sensor.slaapkamer_disney_watch_time") is None


async def test_combined_sums_devices(hass: HomeAssistant, clock: FakeClock) -> None:
    set_lg(hass, "playing", "YouTube")
    hass.states.async_set(CAST, "playing", {"app_name": "YouTube"})
    await setup(
        hass,
        make_entry(
            device_subentry(LG_SUBENTRY, "LG", LG),
            device_subentry(CAST_SUBENTRY, "Slaapkamer", CAST),
        ),
    )
    await clock.advance(60)
    assert minutes(hass, ALL_YOUTUBE) == pytest.approx(2.0, abs=0.1)


async def test_totals_survive_restart(hass: HomeAssistant, clock: FakeClock) -> None:
    set_lg(hass, "playing", "YouTube")
    entry = await setup(hass, lg_entry())
    await clock.advance(120)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    # Reload closed the session and reopened it; nothing lost or doubled.
    assert minutes(hass, LG_YOUTUBE) == pytest.approx(2.0, abs=0.1)
    await clock.advance(60)
    assert minutes(hass, LG_YOUTUBE) == pytest.approx(3.0, abs=0.1)


async def test_missing_media_player_does_not_fail(
    hass: HomeAssistant, clock: FakeClock
) -> None:
    entry = await setup(hass, lg_entry())
    assert entry.state.name == "LOADED"
    assert hass.states.get(LG_ACTIVITY).state == "off"
    set_lg(hass, "playing", "YouTube")
    await hass.async_block_till_done()
    assert hass.states.get(LG_ACTIVITY).state == "YouTube"


async def test_stop_saves_open_session(
    hass: HomeAssistant, clock: FakeClock, hass_storage: dict
) -> None:
    set_lg(hass, "playing", "YouTube")
    await setup(hass, lg_entry())
    await clock.advance(90)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    stored = hass_storage[STORAGE_KEY]["data"]
    assert stored["devices"][LG_SUBENTRY]["youtube"]["minutes"] == pytest.approx(1.5)
    assert stored["combined"]["youtube"]["minutes"] == pytest.approx(1.5)


async def test_loads_stored_totals(
    hass: HomeAssistant, clock: FakeClock, hass_storage: dict
) -> None:
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {
            "devices": {
                LG_SUBENTRY: {"plex": {"display_name": "Plex", "minutes": 90.0}},
                "removed_tv": {"plex": {"display_name": "Plex", "minutes": 30.0}},
            },
            "combined": {"plex": {"display_name": "Plex", "minutes": 120.0}},
        },
    }
    set_lg(hass, "off")
    entry = await setup(hass, lg_entry())
    # A sensor exists for a stored source that isn't in source_list, while the TV is off.
    assert minutes(hass, "sensor.lg_plex_watch_time") == pytest.approx(90.0)
    assert minutes(hass, "sensor.all_tvs_plex_watch_time") == pytest.approx(120.0)
    assert hass.states.get(LG_ACTIVITY).state == "off"
    # Totals of the removed sub-entry were dropped, combined kept.
    assert "removed_tv" not in entry.runtime_data.store.device_ids()


async def test_ignored_source_without_time_is_pruned(
    hass: HomeAssistant, clock: FakeClock, hass_storage: dict
) -> None:
    # Observed: Sonos Beam (an HDMI ARC input on the LG) appeared in the source
    # list and was ignored afterwards; its 0-minute sensors kept coming back.
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {
            "devices": {
                LG_SUBENTRY: {
                    "sonos_beam": {"display_name": "Sonos Beam", "minutes": 0.0},
                    "netflix": {"display_name": "Netflix", "minutes": 30.0},
                }
            },
            "combined": {
                "sonos_beam": {"display_name": "Sonos Beam", "minutes": 0.0},
                "netflix": {"display_name": "Netflix", "minutes": 30.0},
            },
        },
    }
    set_lg(hass, "off")
    entry = await setup(hass, lg_entry())
    ent_reg = er.async_get(hass)
    assert ent_reg.async_get("sensor.lg_sonos_beam_watch_time") is not None

    hass.config_entries.async_update_entry(
        entry,
        options={CONF_NAME_OVERRIDES: "Sonos Beam = !ignore\nNetflix = !ignore"},
    )
    await hass.async_block_till_done()

    for entity_id in (
        "sensor.lg_sonos_beam_watch_time",
        "sensor.all_tvs_sonos_beam_watch_time",
    ):
        assert ent_reg.async_get(entity_id) is None
        assert hass.states.get(entity_id) is None
    store = entry.runtime_data.store
    assert "sonos_beam" not in store.device_totals(LG_SUBENTRY)
    assert "sonos_beam" not in store.combined
    # Recorded time is never dropped, even for a source that is now ignored.
    assert minutes(hass, "sensor.lg_netflix_watch_time") == pytest.approx(30.0)
    assert minutes(hass, "sensor.all_tvs_netflix_watch_time") == pytest.approx(30.0)


async def test_removing_subentry(hass: HomeAssistant, clock: FakeClock) -> None:
    set_lg(hass, "playing", "YouTube")
    entry = await setup(hass, lg_entry())
    await clock.advance(60)

    assert hass.config_entries.async_remove_subentry(entry, LG_SUBENTRY)
    await hass.async_block_till_done()

    assert er.async_get(hass).async_get(LG_YOUTUBE) is None
    assert (
        dr.async_get(hass).async_get_device_by_identifier(
            (DOMAIN, LG_SUBENTRY), entry.entry_id
        )
        is None
    )
    assert LG_SUBENTRY not in entry.runtime_data.store.device_ids()
    assert minutes(hass, ALL_YOUTUBE) == pytest.approx(1.0, abs=0.1)


async def test_source_list_change_creates_new_sensor(
    hass: HomeAssistant, clock: FakeClock
) -> None:
    set_lg(hass, "on")
    await setup(hass, lg_entry())
    assert hass.states.get("sensor.lg_live_tv_watch_time") is None

    hass.states.async_set(
        LG,
        "playing",
        {
            "source_list": LG_SOURCES + ["Live TV"],
            "source": "Live TV",
            "friendly_name": "LG",
        },
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.lg_live_tv_watch_time") is not None
    assert hass.states.get("sensor.all_tvs_live_tv_watch_time") is not None
