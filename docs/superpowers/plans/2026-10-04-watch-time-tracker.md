# Watch Time Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `watch_time_tracker` Home Assistant custom integration: per-TV and combined watch-time sensors per app/source, with a counting mode per source per TV, a grace period, and HACS packaging.

**Architecture:** A pure-Python core (`app_names.py` for detection and name mapping, `tracker.py` for the session state machine with time passed in) is wrapped by thin HA-facing classes. `TrackedDevice` (one per config sub-entry) watches entity states, feeds the tracker and credits totals. `Hub` owns the combined totals. `TotalsStore` persists everything through HA's `Store`. Sensors subscribe to `TrackedDevice`/`Hub` listener callbacks. Any sub-entry or options change reloads the entry.

**Tech Stack:** Python 3.14, Home Assistant 2026.9.4, `pytest-homeassistant-custom-component==0.13.367` (pins HA 2026.9.4), pytest-asyncio (auto mode), freezegun (`freezer` fixture), ruff 0.16.10, GitHub Actions (HACS action, hassfest).

**Spec:** `docs/superpowers/specs/2026-10-03-watch-time-tracker-design.md`

## Global Constraints

- Domain `watch_time_tracker`, name "Watch Time Tracker". GitHub repo `jelle514/WatchTimeTracker`.
- `manifest.json`: `config_flow: true`, `single_config_entry: true`, `integration_type: "hub"`, `iot_class: "calculated"`, `requirements: []`, `version` matches the GitHub release tag.
- `hacs.json`: `name` and `homeassistant: "2026.9.0"`. No `render_readme`.
- Only `translations/en.json`, no `strings.json`.
- Native unit minutes (float, never rounded while accumulating). `suggested_unit_of_measurement: h`, `suggested_display_precision: 1`. `device_class: duration`, `state_class: total_increasing`.
- Unique IDs: `{subentry_id}_activity`, `{subentry_id}_watch_{source_key}`, `combined_watch_{source_key}`.
- The activity sensor never reports a literal `"unknown"` string. "Unknown app" has the source key `unknown_app`. "Unknown app" counts only while the TV reports `playing`, whatever the default mode (the LG home screen reports `on` with no `source`).
- The TV counts as playing when the media player or the extra entity says `playing` (the extra entity only for the same app, or when it names no app); the media player alone decides on/off (Chromecast with Google TV: the Android TV Remote player never says `playing`, its Cast entity does).
- Durations use a monotonic clock (`time.monotonic`). Downtime is never credited.
- `Store` is the only source of truth (no `RestoreSensor`).
- `tracker.py` and `app_names.py` have no Home Assistant imports.
- Entities and devices of a tracked TV are linked to its sub-entry (`async_add_entities(..., config_subentry_id=...)`).
- Hub and devices live in `entry.runtime_data`, not `hass.data`.
- Live tick every 60 s, delayed save ~30 s, grace period default 60 s (0–600 s).

## Notes for implementers

All code in this plan was run against HA 2026.9.4 before the plan was written: every task's tests pass at the end of that task, and ruff is clean. These HA details are easy to get wrong:

- **`config_flow.py` must exist before any config entry can be set up.** HA imports it during entry setup, even in tests. That's why Task 1 creates the main flow.
- **Reconfigure uses `async_update_and_abort`, not `async_update_reload_and_abort`.** The latter raises `ValueError` when the entry has an update listener, and ours does (it reloads on every sub-entry change).
- **HA's `slugify()` returns `"unknown"` for names with no ASCII letters** instead of an empty string. `app_names.make_key` therefore has its own ASCII slug so the spec's hash fallback works and nothing collides with "unknown".
- **Use `hass.bus.async_listen` for `EVENT_HOMEASSISTANT_STOP`, not `async_listen_once`.** Unsubscribing a once-listener after it fired logs an exception, and `entry.async_on_unload` would do exactly that on a later unload. The handler is idempotent.
- **In tests, `device_registry.async_get_device(identifiers=...)` raises in HA 2026.9.** Use `async_get_device_by_identifier((DOMAIN, id), entry.entry_id)`.
- **Sensor updates use listener callbacks** on `Hub`/`TrackedDevice` (`add_new_source_listener`, `add_update_listener`) instead of dispatcher signals. They play the same role as the spec's "new-source signals" without global signal names.
- **Testing time:** the `clock` fixture (in `tests/conftest.py`) patches `custom_components.watch_time_tracker.device.monotonic` and moves HA's frozen time with it, so grace timers and live ticks fire. Always `await clock.advance(seconds)` instead of sleeping.

## File structure

```
.github/workflows/validate.yml     CI: HACS validation, hassfest, ruff, pytest
hacs.json                          HACS metadata
README.md                          Install, setup, counting modes, grace, name mapping
pyproject.toml                     pytest + ruff config
requirements_test.txt              Pinned test/lint dependencies
scripts/make_brand.py              Generates brand/ PNGs
custom_components/watch_time_tracker/
  manifest.json
  const.py          Keys, modes, defaults, fixed names
  app_names.py      Raw app detection, built-in table, overrides, source keys   (pure)
  tracker.py        Counting decision + session state machine                  (pure)
  storage.py        TotalsStore around HA Store
  hub.py            Combined totals + listeners
  device.py         TrackedDevice: state listener, timers, credits
  sensor.py         Activity, per-TV and combined watch-time sensors
  __init__.py       Setup/unload, stale data cleanup, stop handling, reload listener
  config_flow.py    Main flow, options flow, tracked-TV sub-entry flow (2 steps)
  diagnostics.py    Config entry diagnostics
  translations/en.json
  brand/icon.png, icon@2x.png, logo.png, logo@2x.png
tests/
  conftest.py        Fixtures: custom integrations, FakeClock, entry helpers
  test_app_names.py  test_tracker.py      (pure unit tests)
  test_sensor.py     test_config_flow.py  test_diagnostics.py  (HA integration tests)
```

## Ordering

Task 0 (the owner's real-TV check) comes first, as agreed in the design. Tasks 1–8 don't depend on its results: the plan's code is fixed and verified. Task 9 applies the findings (built-in name table, README advice, grace default) once the code exists.

---

### Task 0: Real-TV check (owner, first)

This needs the physical TVs, so the owner does it. It corresponds to the spec's "Before implementation" section. Its results go into a notes file that Task 9 applies.

**Already observed (2026-10-04):** recorded in `docs/superpowers/device-check.md`. Casting F1 TV to the LG:

```
media_player.lg_webos_smart_tv | playing | device_class: tv, source_list: [Disney+, HDMI 4, NPO Start, Netflix, Nintendo Switch Game Console, PC, Plex, Sonos Beam, YouTube]   (no source)
media_player.lg_webos_tv_oled55c34la_2 | playing | app_id: B3E81094, app_name: F1TV Chromecast, media_content_type: video
media_player.lg_webos_tv_oled55c34la | unavailable
```

`..._2` is the LG's built-in Chromecast and becomes the Woonkamer TV's extra activity entity. The test `test_casting_to_lg_uses_builtin_chromecast` (Task 4) replays this observation.

Home screen: the LG reports `on` with no `source` and `..._2` is `off`, which looks exactly like an unknown app. "Unknown app" therefore counts only while `playing`. `test_home_screen_is_not_counted` (Task 4) replays this.

PC on HDMI: the LG reports `on` with `source: PC` and `..._2` is `off`. HDMI sources therefore need the per-source "count whenever open" mode, as designed. `test_per_source_mode` (Task 4) replays this.

**Files:**
- Modify: `docs/superpowers/device-check.md` (started 2026-10-04 with the casting and HDMI observations)

- [ ] **Step 1: Record the states and attributes in each situation**

In Home Assistant, go to **Developer Tools → Template**, paste the following, and copy the output for each situation:

```jinja
{% for s in states.media_player | list + states.remote | list %}
{{ s.entity_id }} | {{ s.state }} | {{ s.attributes | dictsort | selectattr(0, 'in', ['source','source_list','app_name','app_id','current_activity','media_content_type','media_title','device_class']) | list }}
{% endfor %}
```

Situations:
- **Woonkamer TV (LG):**
  - a native app playing (YouTube, Netflix)
  - several short YouTube videos back to back. Run the template between two videos and note roughly how long the gap lasts.
  - another HDMI source (Nintendo Switch), to confirm it behaves like PC
  - the home screen
- **Slaapkamer TV (Chromecast with Google TV):**
  - the home screen
  - YouTube, Netflix, Plex and Disney+, each while playing and while paused

- [ ] **Step 2: Write the notes**

Fill in the "Still to record" sections of `docs/superpowers/device-check.md`: one section per situation, with the pasted output and one line saying what it means: which raw value names the app, which state the TV reports, and the gap length between videos.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/device-check.md
git commit -m "docs: record real-TV states for app detection"
```

---

### Task 1: Scaffold, test harness and main config flow

**Files:**
- Create: `pyproject.toml`, `requirements_test.txt`
- Create: `custom_components/watch_time_tracker/manifest.json`, `const.py`, `__init__.py`, `config_flow.py`, `translations/en.json`
- Create: `tests/__init__.py` (empty), `tests/conftest.py`
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Consumes: nothing.
- Produces: every constant in `const.py` (used by all later tasks). `tests/conftest.py` fixtures/helpers used by every later integration test: `clock` fixture → `FakeClock` with `now: float` and `async advance(seconds: float)`; `device_subentry(subentry_id, title, media_player, *, extra_entity=None, default_mode=MODE_PLAYING_ONLY, grace_period=60, mode_exceptions=None) -> ConfigSubentryDataWithId`; `make_entry(*subentries, options=None) -> MockConfigEntry`; `async setup(hass, entry) -> MockConfigEntry`; `set_lg(hass, state, source=None)`; constants `LG`, `LG_SUBENTRY`, `CAST`, `CAST_REMOTE`, `CAST_SUBENTRY`, `LG_SOURCES`.

- [ ] **Step 1: Create the virtualenv and project config**

`pyproject.toml`:
```toml
[project]
name = "watch-time-tracker"
version = "0.1.0"
requires-python = ">=3.14.2"

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
pythonpath = ["."]

[tool.ruff]
target-version = "py314"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
ignore = ["E501"]  # line length is left to ruff format

[tool.ruff.lint.isort]
known-first-party = ["custom_components"]
force-sort-within-sections = true
combine-as-imports = true
```

`requirements_test.txt`:
```text
pytest-homeassistant-custom-component==0.13.367
ruff==0.16.10
```

Run:
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
```
Expected: installs without errors (`.venv` is already in `.gitignore`).

- [ ] **Step 2: Create the manifest and constants**

`custom_components/watch_time_tracker/manifest.json`:
```json
{
  "domain": "watch_time_tracker",
  "name": "Watch Time Tracker",
  "codeowners": ["@jelle514"],
  "config_flow": true,
  "documentation": "https://github.com/jelle514/WatchTimeTracker",
  "integration_type": "hub",
  "iot_class": "calculated",
  "issue_tracker": "https://github.com/jelle514/WatchTimeTracker/issues",
  "requirements": [],
  "single_config_entry": true,
  "version": "0.1.0"
}
```

`custom_components/watch_time_tracker/const.py`:
```python
"""Constants for Watch Time Tracker."""

from typing import Final

DOMAIN: Final = "watch_time_tracker"

SUBENTRY_TYPE_DEVICE: Final = "device"

# Main entry options
CONF_NAME_OVERRIDES: Final = "name_overrides"

# Sub-entry data
CONF_NAME: Final = "name"
CONF_MEDIA_PLAYER: Final = "media_player"
CONF_EXTRA_ENTITY: Final = "extra_entity"
CONF_DEFAULT_MODE: Final = "default_mode"
CONF_GRACE_PERIOD: Final = "grace_period"
CONF_MODE_EXCEPTIONS: Final = "mode_exceptions"

# Form-only fields of the "sources" step. Two keys so the label can follow
# the default mode; both are stored as CONF_MODE_EXCEPTIONS.
FIELD_COUNT_WHILE_OPEN: Final = "count_while_open"
FIELD_COUNT_ONLY_WHILE_PLAYING: Final = "count_only_while_playing"

MODE_PLAYING_ONLY: Final = "playing_only"
MODE_APP_OPEN: Final = "app_open"
MODES: Final = (MODE_PLAYING_ONLY, MODE_APP_OPEN)

DEFAULT_GRACE_PERIOD: Final = 60
MAX_GRACE_PERIOD: Final = 600

LIVE_TICK_SECONDS: Final = 60
SAVE_DELAY_SECONDS: Final = 30

UNKNOWN_APP_KEY: Final = "unknown_app"
UNKNOWN_APP_NAME: Final = "Unknown app"

# Media player states that never count, whatever the mode
INACTIVE_STATES: Final = frozenset({"off", "unavailable", "unknown", "standby"})
STATE_PLAYING: Final = "playing"

ACTIVITY_IDLE: Final = "idle"
ACTIVITY_OFF: Final = "off"

COMBINED_DEVICE_ID: Final = "combined"
```

- [ ] **Step 3: Write the test fixtures and the failing main-flow tests**

Create an empty `tests/__init__.py` (the tests import helpers with `from .conftest import ...`).

`tests/conftest.py`:
```python
"""Shared fixtures."""

from collections.abc import Generator
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigSubentryDataWithId
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.watch_time_tracker.const import (
    CONF_DEFAULT_MODE,
    CONF_EXTRA_ENTITY,
    CONF_GRACE_PERIOD,
    CONF_MEDIA_PLAYER,
    CONF_MODE_EXCEPTIONS,
    DOMAIN,
    MODE_PLAYING_ONLY,
    SUBENTRY_TYPE_DEVICE,
)

LG = "media_player.lg_webos_smart_tv"
LG_SUBENTRY = "lg_subentry"
CAST = "media_player.chromecast"
CAST_REMOTE = "remote.slaapkamer_tv"
CAST_SUBENTRY = "cast_subentry"

LG_SOURCES = ["YouTube", "Netflix", "PC", "Nintendo Switch Game Console"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let HA load custom_components/ in every test."""


class FakeClock:
    """Moves wall time (timers) and the integration's monotonic clock together."""

    def __init__(self, hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
        self.hass = hass
        self.freezer = freezer
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    async def advance(self, seconds: float) -> None:
        self.now += seconds
        self.freezer.tick(timedelta(seconds=seconds))
        async_fire_time_changed(self.hass)
        await self.hass.async_block_till_done()


@pytest.fixture
def clock(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> Generator[FakeClock]:
    """Fake clock patched into device.py."""
    fake = FakeClock(hass, freezer)
    with patch("custom_components.watch_time_tracker.device.monotonic", fake.monotonic):
        yield fake


def device_subentry(
    subentry_id: str,
    title: str,
    media_player: str,
    *,
    extra_entity: str | None = None,
    default_mode: str = MODE_PLAYING_ONLY,
    grace_period: int = 60,
    mode_exceptions: list[str] | None = None,
) -> ConfigSubentryDataWithId:
    """Sub-entry data for a tracked TV."""
    return ConfigSubentryDataWithId(
        subentry_id=subentry_id,
        subentry_type=SUBENTRY_TYPE_DEVICE,
        title=title,
        unique_id=None,
        data={
            CONF_MEDIA_PLAYER: media_player,
            CONF_EXTRA_ENTITY: extra_entity,
            CONF_DEFAULT_MODE: default_mode,
            CONF_GRACE_PERIOD: grace_period,
            CONF_MODE_EXCEPTIONS: mode_exceptions or [],
        },
    )


def make_entry(
    *subentries: ConfigSubentryDataWithId, options: dict[str, Any] | None = None
) -> MockConfigEntry:
    """Main entry with the given tracked TVs."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Watch Time Tracker",
        data={},
        options=options or {},
        subentries_data=list(subentries),
    )


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> MockConfigEntry:
    """Add and set up an entry."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def set_lg(hass: HomeAssistant, state: str, source: str | None = None) -> None:
    """Set the LG media player state."""
    attributes: dict[str, Any] = {"source_list": LG_SOURCES, "friendly_name": "LG"}
    if source is not None:
        attributes["source"] = source
    hass.states.async_set(LG, state, attributes)
```

`tests/test_config_flow.py`:
```python
"""Tests for the main flow, options flow and tracked-TV sub-entry flow."""

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.watch_time_tracker.const import DOMAIN

from .conftest import make_entry


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
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config_flow.py -q`
Expected: FAIL. The integration can't be loaded yet (no `__init__.py`/`config_flow.py`).

- [ ] **Step 5: Write the minimal integration and main flow**

`custom_components/watch_time_tracker/__init__.py` (replaced in Task 4):
```python
"""Watch Time Tracker: watch time per app per TV."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Watch Time Tracker from a config entry."""
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return True
```

`custom_components/watch_time_tracker/config_flow.py` (extended in Task 6):
```python
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
```

`custom_components/watch_time_tracker/translations/en.json` (extended in Tasks 4 and 6):
```json
{
  "config": {
    "step": {
      "user": {
        "description": "Track how long each app or source is watched on your TVs. After setup, add each TV with \"Add tracked TV\"."
      }
    },
    "abort": {
      "single_instance_allowed": "Watch Time Tracker is already set up. Add more TVs to the existing entry."
    }
  }
}
```

- [ ] **Step 6: Run the tests and lint**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/ruff format --check .`
Expected: `2 passed`, `All checks passed!`, all files formatted.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml requirements_test.txt custom_components tests
git commit -m "feat: scaffold integration, test harness and main config flow"
```

---

### Task 2: App detection, name mapping and source keys

**Files:**
- Create: `custom_components/watch_time_tracker/app_names.py`
- Test: `tests/test_app_names.py`

**Interfaces:**
- Consumes: nothing (no HA imports).
- Produces:
  - `ResolvedApp(key: str, display_name: str)`, a frozen dataclass.
  - `OverrideError(ValueError)` with `.line_number: int` and `.line: str`.
  - `parse_overrides(text: str) -> dict[str, str | None]`. Keys are casefolded; `None` means ignored.
  - `make_key(display_name: str) -> str`
  - `resolve(raw: str, overrides: Mapping[str, str | None]) -> ResolvedApp | None`. Returns `None` when the value is ignored.
  - `raw_app_values(media_attributes: Mapping, extra_attributes: Mapping | None) -> list[str]`: every non-empty candidate, in detection order.
  - `detect_app(media_attributes, extra_attributes, overrides) -> tuple[str | None, ResolvedApp | None]`: the first candidate that isn't ignored. Returns `(None, None)` when there are no candidates (the caller makes it "Unknown app") and `(first raw, None)` when every candidate is ignored.
  - `BUILTIN_NAMES: dict[str, str | None]`, `IGNORE_MARKER = "!ignore"`.

- [ ] **Step 1: Write the failing tests**

`tests/test_app_names.py`:
```python
"""Tests for app name detection, mapping and source keys."""

import pytest

from custom_components.watch_time_tracker.app_names import (
    OverrideError,
    ResolvedApp,
    detect_app,
    make_key,
    parse_overrides,
    raw_app_values,
    resolve,
)


def test_builtin_lookup() -> None:
    assert resolve("com.netflix.ninja", {}) == ResolvedApp("netflix", "Netflix")


def test_builtin_lookup_ignores_case() -> None:
    assert resolve("COM.NETFLIX.NINJA", {}) == ResolvedApp("netflix", "Netflix")


def test_builtin_launcher_is_ignored() -> None:
    assert resolve("com.google.android.apps.tv.launcherx", {}) is None


def test_unknown_value_is_used_unchanged() -> None:
    assert resolve("NPO Start", {}) == ResolvedApp("npo_start", "NPO Start")


def test_override_beats_builtin() -> None:
    overrides = {"com.netflix.ninja": "Netflix NL"}
    assert resolve("com.netflix.ninja", overrides) == ResolvedApp(
        "netflix_nl", "Netflix NL"
    )


def test_override_can_ignore() -> None:
    assert resolve("Sonos Beam", {"sonos beam": None}) is None


def test_parse_overrides() -> None:
    text = "com.foo.bar = Foo\n\n  Sonos Beam = !ignore  \nPC=Gaming PC"
    assert parse_overrides(text) == {
        "com.foo.bar": "Foo",
        "sonos beam": None,
        "pc": "Gaming PC",
    }


@pytest.mark.parametrize(
    ("text", "line_number"),
    [("no equals sign", 1), ("ok = Fine\n= Missing raw", 2), ("raw =   ", 1)],
)
def test_parse_overrides_errors_name_the_line(text: str, line_number: int) -> None:
    with pytest.raises(OverrideError) as err:
        parse_overrides(text)
    assert err.value.line_number == line_number


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("YouTube", "youtube"),
        ("Disney+", "disney"),
        ("NPO Start", "npo_start"),
        ("Nintendo Switch Game Console", "nintendo_switch_game_console"),
        ("Crème Brûlée TV", "creme_brulee_tv"),
        ("Unknown app", "unknown_app"),
    ],
)
def test_make_key(name: str, key: str) -> None:
    assert make_key(name) == key


def test_make_key_empty_slug_uses_hash() -> None:
    key = make_key("📺")
    assert key.startswith("app_")
    assert len(key) == len("app_") + 8
    assert make_key("📺") == key
    assert make_key("🎮") != key


def test_raw_value_detection_order() -> None:
    media = {"app_name": "Netflix"}
    extra = {"current_activity": "com.google.android.youtube.tv", "source": "x"}
    assert raw_app_values(media, extra) == [
        "Netflix",
        "com.google.android.youtube.tv",
        "x",
    ]
    assert raw_app_values({"source": "PC", "app_name": "y"}, None) == ["PC", "y"]
    assert raw_app_values({}, {"source": "  ", "app_name": "Plex"}) == ["Plex"]
    assert raw_app_values({}, None) == []


def test_detect_app_uses_first_value() -> None:
    assert detect_app({"source": "PC"}, {"app_name": "Plex"}, {}) == (
        "PC",
        ResolvedApp("pc", "PC"),
    )


def test_detect_app_skips_ignored_values() -> None:
    # Observed: casting F1 TV to a Chromecast with Google TV. The Android TV
    # Remote player reports the Cast receiver; the Cast entity names the app.
    media = {"app_name": "com.google.android.apps.mediashell"}
    extra = {"app_name": "F1TV Chromecast"}
    assert detect_app(media, extra, {}) == (
        "F1TV Chromecast",
        ResolvedApp("f1tv_chromecast", "F1TV Chromecast"),
    )


def test_detect_app_all_ignored() -> None:
    launcher = "com.google.android.apps.tv.launcherx"
    assert detect_app({"app_name": launcher}, {"current_activity": launcher}, {}) == (
        launcher,
        None,
    )


def test_detect_app_nothing_to_detect() -> None:
    assert detect_app({}, None, {}) == (None, None)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_app_names.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.watch_time_tracker.app_names'`.

- [ ] **Step 3: Implement**

`custom_components/watch_time_tracker/app_names.py`:
```python
"""App name detection, mapping and source keys. No Home Assistant imports."""

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import re
from typing import Any
import unicodedata

IGNORE_MARKER = "!ignore"

# Raw value (casefolded) -> display name, or None to ignore the value.
# Extend with the values recorded during the pre-implementation device check.
BUILTIN_NAMES: dict[str, str | None] = {
    "com.google.android.youtube.tv": "YouTube",
    "com.netflix.ninja": "Netflix",
    "com.disney.disneyplus": "Disney+",
    "com.plexapp.android": "Plex",
    "nl.uitzendinggemist": "NPO Start",
    "com.amazon.amazonvideo.livingroom": "Prime Video",
    "com.spotify.tv.android": "Spotify",
    # Home screens / launchers
    "com.google.android.apps.tv.launcherx": None,
    "com.google.android.tvlauncher": None,
    # Cast receiver on Google TV: the real app name comes from the Cast entity
    "com.google.android.apps.mediashell": None,
}

_RAW_ATTRIBUTE_ORDER: tuple[tuple[str, str], ...] = (
    ("media", "source"),
    ("media", "app_name"),
    ("extra", "current_activity"),
    ("extra", "source"),
    ("extra", "app_name"),
)


@dataclass(frozen=True)
class ResolvedApp:
    """An app after name mapping."""

    key: str
    display_name: str


class OverrideError(ValueError):
    """An override line could not be parsed."""

    def __init__(self, line_number: int, line: str) -> None:
        super().__init__(f"Invalid override on line {line_number}: {line!r}")
        self.line_number = line_number
        self.line = line


def parse_overrides(text: str) -> dict[str, str | None]:
    """Parse `raw = Display Name` / `raw = !ignore` lines.

    Blank lines are skipped. Keys are casefolded. None means ignored.
    """
    overrides: dict[str, str | None] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        raw, sep, name = line.partition("=")
        raw, name = raw.strip(), name.strip()
        if not sep or not raw or not name:
            raise OverrideError(number, line)
        overrides[raw.casefold()] = None if name == IGNORE_MARKER else name
    return overrides


def make_key(display_name: str) -> str:
    """Return the source key for a display name.

    ASCII slug of the name; `app_` + 8 hex chars of its SHA-1 if that is empty.
    """
    ascii_name = (
        unicodedata.normalize("NFKD", display_name)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_name.lower()).strip("_")
    if slug:
        return slug
    return "app_" + hashlib.sha1(display_name.encode("utf-8")).hexdigest()[:8]


def resolve(raw: str, overrides: Mapping[str, str | None]) -> ResolvedApp | None:
    """Resolve a raw app value. Returns None if the value is ignored."""
    folded = raw.casefold()
    if folded in overrides:
        name = overrides[folded]
    elif folded in BUILTIN_NAMES:
        name = BUILTIN_NAMES[folded]
    else:
        name = raw
    if name is None:
        return None
    return ResolvedApp(make_key(name), name)


def raw_app_values(
    media_attributes: Mapping[str, Any],
    extra_attributes: Mapping[str, Any] | None,
) -> list[str]:
    """Return every non-empty raw app value, in the spec's detection order."""
    sources = {"media": media_attributes, "extra": extra_attributes or {}}
    values = []
    for source, attribute in _RAW_ATTRIBUTE_ORDER:
        value = sources[source].get(attribute)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return values


def detect_app(
    media_attributes: Mapping[str, Any],
    extra_attributes: Mapping[str, Any] | None,
    overrides: Mapping[str, str | None],
) -> tuple[str | None, ResolvedApp | None]:
    """Return (raw value, app) for the first raw value that isn't ignored.

    (None, None) when there is no raw value at all (an unknown app);
    (first raw value, None) when every raw value is ignored.
    """
    values = raw_app_values(media_attributes, extra_attributes)
    for raw in values:
        if (resolved := resolve(raw, overrides)) is not None:
            return raw, resolved
    return (values[0] if values else None), None
```

- [ ] **Step 4: Run the tests and lint**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/ruff format --check .`
Expected: `24 passed`, lint clean.

- [ ] **Step 5: Commit**

```bash
git add custom_components/watch_time_tracker/app_names.py tests/test_app_names.py
git commit -m "feat: add app detection, name mapping and source keys"
```

---

### Task 3: Counting decision and session state machine

**Files:**
- Create: `custom_components/watch_time_tracker/tracker.py`
- Test: `tests/test_tracker.py`

**Interfaces:**
- Consumes: `const.py` (`INACTIVE_STATES`, `MODE_APP_OPEN`, `MODE_PLAYING_ONLY`, `STATE_PLAYING`, `UNKNOWN_APP_KEY`).
- Produces:
  - `type Credit = tuple[str, float]`, meaning (source_key, minutes).
  - States: `Idle()`, `Counting(app: str, since: float)`, `Grace(app: str, since: float, gap_start: float)`. All are frozen dataclasses.
  - `combined_player_state(player_state: str | None, extra_state: str | None, extra_app: str | None, app: str | None) -> str | None`: the media player decides on/off; the extra entity's `playing` counts only when `extra_app` (its own source key, or None) is None or equals `app`.
  - `effective_mode(app_key: str, default_mode: str, exceptions: Collection[str]) -> str`
  - `counting_app(player_state: str | None, app_key: str | None, default_mode: str, exceptions: Collection[str]) -> str | None`
  - `Tracker(grace_period: float)` with:
    - attributes `.grace_period` and `.state`
    - `update(app: str | None, now: float) -> list[Credit]`
    - `tick(now: float) -> list[Credit]`
    - `grace_expired() -> list[Credit]`
    - `close(now: float) -> list[Credit]`

- [ ] **Step 1: Write the failing tests**

`tests/test_tracker.py`:
```python
"""Tests for the watch session state machine (fake clock, no HA)."""

import pytest

from custom_components.watch_time_tracker.const import (
    MODE_APP_OPEN,
    MODE_PLAYING_ONLY,
    UNKNOWN_APP_KEY,
)
from custom_components.watch_time_tracker.tracker import (
    Counting,
    Grace,
    Idle,
    Tracker,
    combined_player_state,
    counting_app,
    effective_mode,
)


def total(credits: list[tuple[str, float]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, minutes in credits:
        out[key] = out.get(key, 0) + minutes
    return out


def test_short_gap_is_fully_counted() -> None:
    t = Tracker(grace_period=60)
    credits = t.update("youtube", 0)
    credits += t.update(None, 300)  # gap between two videos
    credits += t.update("youtube", 320)
    credits += t.close(600)
    assert total(credits) == {"youtube": 10.0}


def test_gap_longer_than_grace_is_not_counted() -> None:
    t = Tracker(grace_period=60)
    t.update("youtube", 0)
    assert t.update(None, 120) == []
    assert isinstance(t.state, Grace)
    assert t.grace_expired() == [("youtube", 2.0)]
    assert t.state == Idle()


def test_switching_apps_during_grace_does_not_count_gap() -> None:
    t = Tracker(grace_period=60)
    t.update("youtube", 0)
    t.update(None, 60)
    assert t.update("netflix", 90) == [("youtube", 1.0)]
    assert t.state == Counting("netflix", 90)


def test_off_during_grace_keeps_grace() -> None:
    t = Tracker(grace_period=60)
    t.update("youtube", 0)
    t.update(None, 60)  # paused
    assert t.update(None, 70) == []  # off
    assert t.state == Grace("youtube", 0, 60)


def test_same_app_update_is_noop() -> None:
    t = Tracker(grace_period=60)
    t.update("youtube", 0)
    assert t.update("youtube", 30) == []
    assert t.state == Counting("youtube", 0)


def test_idle_not_counting_is_noop() -> None:
    t = Tracker(grace_period=60)
    assert t.update(None, 10) == []
    assert t.state == Idle()


def test_switching_apps_credits_previous() -> None:
    t = Tracker(grace_period=60)
    t.update("youtube", 0)
    assert t.update("netflix", 180) == [("youtube", 3.0)]


def test_grace_zero_closes_immediately() -> None:
    t = Tracker(grace_period=0)
    t.update("youtube", 0)
    assert t.update(None, 60) == [("youtube", 1.0)]
    assert t.state == Idle()


def test_live_ticks_do_not_double_count() -> None:
    t = Tracker(grace_period=60)
    t.update("youtube", 0)
    credits = t.tick(60) + t.tick(120)
    credits += t.update(None, 150)
    credits += t.grace_expired()
    assert total(credits) == pytest.approx({"youtube": 2.5})


def test_tick_during_grace_credits_nothing() -> None:
    t = Tracker(grace_period=60)
    t.update("youtube", 0)
    t.update(None, 30)
    assert t.tick(60) == []


def test_negative_difference_credits_nothing() -> None:
    t = Tracker(grace_period=0)
    t.update("youtube", 100)
    assert t.tick(50) == []
    assert t.update(None, 90) == []


def test_close_during_counting() -> None:
    t = Tracker(grace_period=60)
    t.update("youtube", 0)
    assert t.close(120) == [("youtube", 2.0)]
    assert t.state == Idle()


def test_close_during_grace_credits_up_to_gap_start() -> None:
    t = Tracker(grace_period=60)
    t.update("youtube", 0)
    t.update(None, 120)
    assert t.close(150) == [("youtube", 2.0)]


@pytest.mark.parametrize(
    ("state", "mode", "expected"),
    [
        ("playing", MODE_PLAYING_ONLY, "youtube"),
        ("paused", MODE_PLAYING_ONLY, None),
        ("on", MODE_PLAYING_ONLY, None),
        ("playing", MODE_APP_OPEN, "youtube"),
        ("paused", MODE_APP_OPEN, "youtube"),
        ("on", MODE_APP_OPEN, "youtube"),
        ("idle", MODE_APP_OPEN, "youtube"),
        ("off", MODE_APP_OPEN, None),
        ("standby", MODE_APP_OPEN, None),
        ("unavailable", MODE_APP_OPEN, None),
        ("unknown", MODE_APP_OPEN, None),
    ],
)
def test_counting_modes(state: str, mode: str, expected: str | None) -> None:
    assert counting_app(state, "youtube", mode, set()) == expected


def test_ignored_app_and_missing_player_never_count() -> None:
    assert counting_app("playing", None, MODE_PLAYING_ONLY, set()) is None
    assert counting_app("on", None, MODE_APP_OPEN, set()) is None
    assert counting_app(None, "youtube", MODE_APP_OPEN, set()) is None


def test_per_source_mode_on_one_tv() -> None:
    exceptions = {"pc"}
    # HDMI source counts while merely on; the app only while playing.
    assert counting_app("on", "pc", MODE_PLAYING_ONLY, exceptions) == "pc"
    assert counting_app("on", "youtube", MODE_PLAYING_ONLY, exceptions) is None
    assert (
        counting_app("playing", "youtube", MODE_PLAYING_ONLY, exceptions) == "youtube"
    )


def test_exceptions_flip_app_open_default() -> None:
    assert effective_mode("plex", MODE_APP_OPEN, {"plex"}) == MODE_PLAYING_ONLY
    assert counting_app("paused", "plex", MODE_APP_OPEN, {"plex"}) is None


def test_unknown_app_counts_only_while_playing() -> None:
    for default in (MODE_PLAYING_ONLY, MODE_APP_OPEN):
        assert effective_mode(UNKNOWN_APP_KEY, default, {UNKNOWN_APP_KEY}) == (
            MODE_PLAYING_ONLY
        )
    assert counting_app("on", UNKNOWN_APP_KEY, MODE_APP_OPEN, set()) is None
    assert counting_app("playing", UNKNOWN_APP_KEY, MODE_APP_OPEN, set()) == (
        UNKNOWN_APP_KEY
    )


def test_switching_between_sources_with_different_modes() -> None:
    exceptions = {"pc"}
    t = Tracker(grace_period=60)
    # PC (while open) for 10 min, then YouTube which is on but not yet playing.
    t.update(counting_app("on", "pc", MODE_PLAYING_ONLY, exceptions), 0)
    credits = t.update(
        counting_app("on", "youtube", MODE_PLAYING_ONLY, exceptions), 600
    )
    assert credits == []  # PC enters grace; YouTube isn't counting yet
    credits = t.update(
        counting_app("playing", "youtube", MODE_PLAYING_ONLY, exceptions), 620
    )
    assert credits == [("pc", 10.0)]
    assert t.state == Counting("youtube", 620)


def test_extra_entity_playing_counts_as_playing() -> None:
    # Observed on a Chromecast with Google TV: the Android TV Remote player
    # says "on", the Cast entity says "playing" for the same app.
    assert combined_player_state("on", "playing", "youtube", "youtube") == "playing"
    assert combined_player_state("on", "playing", None, "youtube") == "playing"
    assert combined_player_state("playing", "off", None, "youtube") == "playing"
    assert combined_player_state("on", "paused", "youtube", "youtube") == "on"
    assert combined_player_state("on", None, None, "youtube") == "on"


def test_extra_entity_playing_for_another_app_is_ignored() -> None:
    # Observed: a phone kept an F1 TV cast session open while Disney+ was on
    # screen; the Cast entity kept reporting F1 TV.
    assert combined_player_state("on", "playing", "f1tv_chromecast", "disney") == "on"


def test_main_player_decides_off() -> None:
    assert combined_player_state("off", "playing", None, None) == "off"
    assert combined_player_state("unavailable", "playing", None, None) == (
        "unavailable"
    )
    assert combined_player_state(None, "playing", None, None) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_tracker.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.watch_time_tracker.tracker'`.

- [ ] **Step 3: Implement**

`custom_components/watch_time_tracker/tracker.py`:
```python
"""Watch session state machine. No Home Assistant imports; time is passed in."""

from collections.abc import Collection
from dataclasses import dataclass

from .const import (
    INACTIVE_STATES,
    MODE_APP_OPEN,
    MODE_PLAYING_ONLY,
    STATE_PLAYING,
    UNKNOWN_APP_KEY,
)

type Credit = tuple[str, float]
"""(source_key, minutes)"""


@dataclass(frozen=True)
class Idle:
    """Nothing is being counted."""


@dataclass(frozen=True)
class Counting:
    """`app` has been counted since `since`."""

    app: str
    since: float


@dataclass(frozen=True)
class Grace:
    """`app` stopped counting at `gap_start`; it may resume within the grace period."""

    app: str
    since: float
    gap_start: float


type TrackerState = Idle | Counting | Grace


def effective_mode(app_key: str, default_mode: str, exceptions: Collection[str]) -> str:
    """Return the counting mode for an app on one device."""
    if app_key == UNKNOWN_APP_KEY:
        # Without a known app (e.g. a home screen), only playback shows watching.
        return MODE_PLAYING_ONLY
    if app_key not in exceptions:
        return default_mode
    return MODE_APP_OPEN if default_mode == MODE_PLAYING_ONLY else MODE_PLAYING_ONLY


def combined_player_state(
    player_state: str | None,
    extra_state: str | None,
    extra_app: str | None,
    app: str | None,
) -> str | None:
    """The media player decides on/off; either entity can say it is playing.

    E.g. a Chromecast with Google TV: the Android TV Remote player knows on/off
    and the app but never says "playing"; its Google Cast entity does.
    The extra entity's "playing" only counts when it names no app or the same
    app (`extra_app` == `app`, both source keys): a cast session left open on a
    phone keeps reporting its own app while another app is on screen.
    """
    if player_state is None or player_state in INACTIVE_STATES:
        return player_state
    if extra_state == STATE_PLAYING and extra_app in (None, app):
        return STATE_PLAYING
    return player_state


def counting_app(
    player_state: str | None,
    app_key: str | None,
    default_mode: str,
    exceptions: Collection[str],
) -> str | None:
    """Return the app being counted, or None for NotCounting.

    `player_state` is None when the media player doesn't exist.
    `app_key` is None when the app is ignored.
    """
    if app_key is None or player_state is None:
        return None
    if effective_mode(app_key, default_mode, exceptions) == MODE_PLAYING_ONLY:
        active = player_state == STATE_PLAYING
    else:
        active = player_state not in INACTIVE_STATES
    return app_key if active else None


def _credit(app: str, start: float, end: float) -> list[Credit]:
    if end <= start:
        return []
    return [(app, (end - start) / 60)]


class Tracker:
    """Turns a stream of situations into watch-time credits."""

    def __init__(self, grace_period: float) -> None:
        self.grace_period = grace_period
        self.state: TrackerState = Idle()

    def update(self, app: str | None, now: float) -> list[Credit]:
        """Feed the current situation: an app key (Counting) or None (NotCounting)."""
        state = self.state
        match state:
            case Idle():
                if app is not None:
                    self.state = Counting(app, now)
                return []
            case Counting():
                if app == state.app:
                    return []
                if app is None:
                    if self.grace_period <= 0:
                        self.state = Idle()
                        return _credit(state.app, state.since, now)
                    self.state = Grace(state.app, state.since, now)
                    return []
                self.state = Counting(app, now)
                return _credit(state.app, state.since, now)
            case Grace():
                if app is None:
                    return []
                if app == state.app:
                    self.state = Counting(app, state.since)
                    return []
                self.state = Counting(app, now)
                return _credit(state.app, state.since, state.gap_start)

    def tick(self, now: float) -> list[Credit]:
        """Credit the running session so far."""
        state = self.state
        if not isinstance(state, Counting):
            return []
        if now <= state.since:
            return []
        self.state = Counting(state.app, now)
        return _credit(state.app, state.since, now)

    def grace_expired(self) -> list[Credit]:
        """The grace period ran out without the app coming back."""
        state = self.state
        if not isinstance(state, Grace):
            return []
        self.state = Idle()
        return _credit(state.app, state.since, state.gap_start)

    def close(self, now: float) -> list[Credit]:
        """Shutdown/unload: close any open session."""
        state = self.state
        self.state = Idle()
        match state:
            case Counting():
                return _credit(state.app, state.since, now)
            case Grace():
                return _credit(state.app, state.since, state.gap_start)
        return []
```

- [ ] **Step 4: Run the tests and lint**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/ruff format --check .`
Expected: `56 passed`, lint clean.

- [ ] **Step 5: Commit**

```bash
git add custom_components/watch_time_tracker/tracker.py tests/test_tracker.py
git commit -m "feat: add counting decision and session state machine"
```

---

### Task 4: Tracking core: storage, hub, tracked device and sensors

**Files:**
- Create: `custom_components/watch_time_tracker/storage.py`, `hub.py`, `device.py`, `sensor.py`
- Modify: `custom_components/watch_time_tracker/__init__.py` (full replacement)
- Modify: `custom_components/watch_time_tracker/translations/en.json` (full replacement, adds `entity`)
- Test: `tests/test_sensor.py`

**Interfaces:**
- Consumes: Task 2 (`resolve`, `detect_app`, `parse_overrides`, `OverrideError`, `ResolvedApp`), Task 3 (`Tracker`, `Counting`, `Grace`, `Credit`, `counting_app`, `effective_mode`), Task 1 constants and test helpers.
- Produces:
  - `storage.py`: `SourceTotal` (TypedDict with `display_name: str`, `minutes: float`), `type Totals = dict[str, SourceTotal]`, `STORAGE_KEY`, and `TotalsStore(hass)` with:
    - `async_load()`
    - `.combined -> Totals`
    - `device_totals(subentry_id) -> Totals`
    - `device_ids() -> list[str]`
    - `remove_device(subentry_id)`
    - `schedule_save()`
    - `async_save()`
  - `hub.py`: `Hub(store)` with:
    - `.totals`
    - `ensure_source(key, display_name)`
    - `add_minutes(key, display_name, minutes)`
    - `add_new_source_listener(cb: Callable[[str], None]) -> CALLBACK_TYPE`
    - `add_update_listener(cb) -> CALLBACK_TYPE`
  - `device.py`: `TrackedDevice(hass, hub, store, subentry: ConfigSubentry, overrides)` with:
    - `.subentry_id`, `.name`, `.media_player`, `.extra_entity`, `.default_mode`, `.mode_exceptions`, `.totals`, `.activity`, `.raw_app`, `.resolved_app`
    - `async_start()`, `async_stop()` (idempotent)
    - `ensure_source(key, display_name)`, `display_name(key)`
    - `add_new_source_listener(...)`, `add_update_listener(...)`
    - `diagnostics() -> dict`
  - `__init__.py`: `RuntimeData(store, hub, devices: dict[str, TrackedDevice])`, `type WatchTimeConfigEntry = ConfigEntry[RuntimeData]`, `PLATFORMS`.
  - Entity IDs used by tests (device "LG", combined device "All TVs"): `sensor.lg_activity`, `sensor.lg_youtube_watch_time`, `sensor.all_tvs_youtube_watch_time`.
  - `test_cast_session_for_ignored_app_is_ignored`: an extra entity whose app is ignored never supplies `playing` (only "no raw candidate at all" counts as naming no app; `device.py` passes the `_IGNORED_EXTRA_APP` sentinel). Added in review.
  - `test_stale_cast_session_is_ignored` replays a phone keeping an F1 TV cast session open while Disney+ is on screen: the Cast entity's `playing` is for another app, so Disney+ isn't counted.
  - `test_casting_app_without_google_tv_app` replays casting F1 TV to the Slaapkamer TV: the Android TV Remote player reports the ignored Cast receiver (`com.google.android.apps.mediashell`), so the app name comes from the Cast entity.
  - `test_google_tv_cast_entity_supplies_playing` replays the Slaapkamer TV observations: Android TV Remote player `on` with a package name + Cast entity `playing` → counted; launcher + Cast `off` → not counted.
  - `test_home_screen_is_not_counted` replays the Task 0 home-screen observation (LG `on`, no `source`, `app_open` default → not counted, activity `idle`).
  - `test_casting_to_lg_uses_builtin_chromecast` replays the Task 0 observation: LG `playing` with no `source`, plus `media_player.lg_webos_tv_oled55c34la_2` reporting `app_name: F1TV Chromecast`.

- [ ] **Step 1: Write the failing tests**

`tests/test_sensor.py`:
```python
"""End-to-end tracking: entity states in, sensor states out."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest

from custom_components.watch_time_tracker.const import (
    CONF_NAME_OVERRIDES,
    DOMAIN,
    MODE_APP_OPEN,
)

from .conftest import (
    CAST,
    CAST_REMOTE,
    CAST_SUBENTRY,
    LG,
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
    assert hass.states.get(LG_ACTIVITY).state == "F1TV Chromecast"
    await clock.advance(60)
    assert minutes(hass, "sensor.lg_f1tv_chromecast_watch_time") == pytest.approx(
        1.0, abs=0.1
    )


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
    assert hass.states.get("sensor.slaapkamer_activity").state == "F1TV Chromecast"
    await clock.advance(60)
    assert minutes(
        hass, "sensor.slaapkamer_f1tv_chromecast_watch_time"
    ) == pytest.approx(1.0, abs=0.1)


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_sensor.py -q`
Expected: FAIL. No sensors exist yet (`AssertionError` / `KeyError` on missing states).

- [ ] **Step 3: Implement storage**

`custom_components/watch_time_tracker/storage.py`:
```python
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
```

- [ ] **Step 4: Implement the hub**

`custom_components/watch_time_tracker/hub.py`:
```python
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
```

- [ ] **Step 5: Implement the tracked device**

`custom_components/watch_time_tracker/device.py`:
```python
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
```

Key behaviour to preserve:
- `_evaluate` runs on every state change of the media player or extra entity. It syncs `source_list` into sensors, detects the app with `detect_app` (ignored candidates are skipped; no candidate at all → "Unknown app"), detects the extra entity's own app (`detect_app({}, extra.attributes, overrides)`) and combines the two entities' states with `combined_player_state`, asks `counting_app` for the per-source mode decision, feeds the tracker, then syncs timers and the activity state.
- The grace timer exists only while the tracker is in `Grace`, and the 60 s live tick only while it is in `Counting`.

- [ ] **Step 6: Implement the sensors**

`custom_components/watch_time_tracker/sensor.py`:
```python
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
```

- [ ] **Step 7: Replace `__init__.py` with the core setup**

`custom_components/watch_time_tracker/__init__.py` (Task 5 adds stale-data cleanup, stop handling and the reload listener):
```python
"""Watch Time Tracker: watch time per app per TV."""

from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .app_names import OverrideError, parse_overrides
from .const import CONF_NAME_OVERRIDES, SUBENTRY_TYPE_DEVICE
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

    try:
        overrides = parse_overrides(entry.options.get(CONF_NAME_OVERRIDES, ""))
    except OverrideError as err:
        _LOGGER.error("Ignoring name overrides: %s", err)
        overrides = {}

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
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WatchTimeConfigEntry) -> bool:
    """Close open sessions, save, and unload."""
    await _async_close_sessions(entry.runtime_data)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_close_sessions(runtime: RuntimeData) -> None:
    for device in runtime.devices.values():
        device.async_stop()
    await runtime.store.async_save()
```

- [ ] **Step 8: Add entity translations**

`custom_components/watch_time_tracker/translations/en.json`:
```json
{
  "config": {
    "step": {
      "user": {
        "description": "Track how long each app or source is watched on your TVs. After setup, add each TV with \"Add tracked TV\"."
      }
    },
    "abort": {
      "single_instance_allowed": "Watch Time Tracker is already set up. Add more TVs to the existing entry."
    }
  },
  "entity": {
    "sensor": {
      "watch_time": {
        "name": "{app} watch time"
      },
      "activity": {
        "name": "Activity"
      }
    }
  }
}
```

The `{app}` placeholder comes from each sensor's `_attr_translation_placeholders`, so the entity name is e.g. "YouTube watch time".

- [ ] **Step 9: Run the tests and lint**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/ruff format --check .`
Expected: `72 passed`, lint clean.

- [ ] **Step 10: Commit**

```bash
git add custom_components tests/test_sensor.py
git commit -m "feat: track watch time per TV and combined, with sensors"
```

---

### Task 5: Lifecycle: stop, stale data cleanup and reload on changes

**Files:**
- Modify: `custom_components/watch_time_tracker/__init__.py` (full replacement)
- Test: `tests/test_sensor.py` (add imports, append 3 tests)

**Interfaces:**
- Consumes: Task 4 (`TotalsStore.device_ids/remove_device`, `RuntimeData`, `_async_close_sessions`).
- Produces: the final `__init__.py`. Any sub-entry add/change/remove or options change reloads the entry, so later tasks (config flow) can rely on that.

- [ ] **Step 1: Write the failing tests**

In `tests/test_sensor.py`, add these imports to the existing import block (keep the existing ones; ruff's isort order is enforced):

```python
from homeassistant.const import EVENT_HOMEASSISTANT_STOP

from custom_components.watch_time_tracker.storage import STORAGE_KEY
```

Append to `tests/test_sensor.py`:
```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_sensor.py -q`
Expected: 3 failures:
- `test_stop_saves_open_session`: stored minutes are `0.0`, not `1.5`.
- `test_loads_stored_totals`: `removed_tv` is still stored.
- `test_removing_subentry`: the removed TV's totals are still stored.

- [ ] **Step 3: Implement**

Replace `custom_components/watch_time_tracker/__init__.py`:
```python
"""Watch Time Tracker: watch time per app per TV."""

from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant

from .app_names import OverrideError, parse_overrides
from .const import CONF_NAME_OVERRIDES, SUBENTRY_TYPE_DEVICE
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

    try:
        overrides = parse_overrides(entry.options.get(CONF_NAME_OVERRIDES, ""))
    except OverrideError as err:
        _LOGGER.error("Ignoring name overrides: %s", err)
        overrides = {}

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
```

- [ ] **Step 4: Run the tests and lint**

Run: `.venv/bin/ruff check --fix tests/test_sensor.py && .venv/bin/ruff format . && .venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/ruff format --check .`
Expected: `75 passed`, lint clean.

- [ ] **Step 5: Commit**

```bash
git add custom_components/watch_time_tracker/__init__.py tests/test_sensor.py
git commit -m "feat: save on stop, drop removed TVs' data, reload on changes"
```

---

### Task 6: Options flow and tracked-TV sub-entry flow

**Files:**
- Modify: `custom_components/watch_time_tracker/config_flow.py` (full replacement)
- Modify: `custom_components/watch_time_tracker/translations/en.json` (full replacement)
- Test: `tests/test_config_flow.py` (full replacement; the 2 main-flow tests are kept)

**Interfaces:**
- Consumes: Task 2 (`parse_overrides`, `OverrideError`, `resolve`), Task 4 (`entry.runtime_data.devices[subentry_id].totals` for stored sources on reconfigure, `TrackedDevice.ensure_source` in tests), Task 5 (reload on sub-entry change).
- Produces:
  - Options data `{name_overrides: str}`.
  - Sub-entry data: `media_player`, `extra_entity`, `default_mode`, `grace_period`, `mode_exceptions: list[str]` (sorted source keys). The title is the name.
  - Flow step IDs: `user` / `reconfigure` → `sources`. Abort reason `already_tracked`.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_config_flow.py`:
```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config_flow.py -q`
Expected: the 2 main-flow tests pass. The others fail: no options flow (`UnknownHandler` / `data_entry_flow.UnknownHandler`) and no sub-entry support (`Config entry 'watch_time_tracker' does not support subentry 'device'`).

- [ ] **Step 3: Implement the flows**

Replace `custom_components/watch_time_tracker/config_flow.py`:
```python
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
            self._data = {
                CONF_NAME: name,
                CONF_MEDIA_PLAYER: media_player,
                CONF_EXTRA_ENTITY: user_input.get(CONF_EXTRA_ENTITY),
                CONF_DEFAULT_MODE: user_input[CONF_DEFAULT_MODE],
                CONF_GRACE_PERIOD: int(user_input[CONF_GRACE_PERIOD]),
                CONF_MODE_EXCEPTIONS: current.get(CONF_MODE_EXCEPTIONS, []),
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
            for value in user_input.get(field, []):
                if resolved := resolve(value, overrides):
                    keys.add(resolved.key)
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
        return self.async_show_form(step_id="sources", data_schema=schema)

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
```

Design notes:
- The "sources" step uses one of two field keys (`count_while_open` / `count_only_while_playing`), so the label follows the default mode. Both are stored as `mode_exceptions`.
- Option values are source keys and labels are display names. Typed custom values go through `resolve()`, and so do known keys, which resolve to themselves. Everything is stored as keys.
- Reconfigure finishes with `async_update_and_abort`. The update listener from Task 5 does the reload.

- [ ] **Step 4: Replace the translations**

`custom_components/watch_time_tracker/translations/en.json`:
```json
{
  "config": {
    "step": {
      "user": {
        "description": "Track how long each app or source is watched on your TVs. After setup, add each TV with \"Add tracked TV\"."
      }
    },
    "abort": {
      "single_instance_allowed": "Watch Time Tracker is already set up. Add more TVs to the existing entry."
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "App name overrides",
        "description": "One mapping per line: `raw value = Display Name`. Use `raw value = !ignore` to never count a value (for example a home screen launcher).",
        "data": {
          "name_overrides": "Overrides"
        }
      }
    },
    "error": {
      "invalid_override": "Line {line_number} is not valid: `{line}`. Use `raw value = Display Name` or `raw value = !ignore`."
    }
  },
  "config_subentries": {
    "device": {
      "entry_type": "Tracked TV",
      "initiate_flow": {
        "user": "Add tracked TV",
        "reconfigure": "Reconfigure tracked TV"
      },
      "step": {
        "user": {
          "title": "Add tracked TV",
          "data": {
            "name": "Name",
            "media_player": "Media player",
            "extra_entity": "Extra activity entity",
            "default_mode": "Default counting mode",
            "grace_period": "Grace period"
          },
          "data_description": {
            "name": "Leave empty to use the media player's name.",
            "extra_entity": "Optional. A remote or media player that reports the current app when the media player doesn't.",
            "default_mode": "How sources on this TV are counted, unless you pick them in the next step.",
            "grace_period": "Short pauses up to this long count as watching."
          }
        },
        "reconfigure": {
          "title": "Reconfigure tracked TV",
          "data": {
            "name": "Name",
            "media_player": "Media player",
            "extra_entity": "Extra activity entity",
            "default_mode": "Default counting mode",
            "grace_period": "Grace period"
          },
          "data_description": {
            "name": "Leave empty to use the media player's name.",
            "extra_entity": "Optional. A remote or media player that reports the current app when the media player doesn't.",
            "default_mode": "How sources on this TV are counted, unless you pick them in the next step.",
            "grace_period": "Short pauses up to this long count as watching."
          }
        },
        "sources": {
          "title": "Counting mode per source",
          "description": "Pick the sources on this TV that use the other counting mode. You can type an app that hasn't been seen yet.",
          "data": {
            "count_while_open": "Sources that count whenever they're open",
            "count_only_while_playing": "Sources that count only while playing"
          },
          "data_description": {
            "count_while_open": "For sources that never report playing, such as HDMI inputs and game consoles.",
            "count_only_while_playing": "For apps that reliably report playing."
          }
        }
      },
      "abort": {
        "already_tracked": "This media player is already tracked by another TV.",
        "reconfigure_successful": "The TV was reconfigured."
      }
    }
  },
  "selector": {
    "default_mode": {
      "options": {
        "playing_only": "Only while playing",
        "app_open": "Whenever an app is open"
      }
    }
  },
  "entity": {
    "sensor": {
      "watch_time": {
        "name": "{app} watch time"
      },
      "activity": {
        "name": "Activity"
      }
    }
  }
}
```

- [ ] **Step 5: Run the tests and lint**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/ruff format --check .`
Expected: `82 passed`, lint clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/watch_time_tracker/config_flow.py custom_components/watch_time_tracker/translations/en.json tests/test_config_flow.py
git commit -m "feat: add name override options and tracked TV sub-entry flow"
```

---

### Task 7: Diagnostics

**Files:**
- Create: `custom_components/watch_time_tracker/diagnostics.py`
- Test: `tests/test_diagnostics.py`

**Interfaces:**
- Consumes: `RuntimeData`, `TrackedDevice.diagnostics()`, `Hub.totals`.
- Produces: `async_get_config_entry_diagnostics(hass, entry) -> dict` with keys `options`, `devices` (per sub-entry ID), `combined`.

- [ ] **Step 1: Write the failing test**

`tests/test_diagnostics.py`:
```python
"""Tests for diagnostics."""

from homeassistant.core import HomeAssistant

from custom_components.watch_time_tracker.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import (
    LG,
    LG_SUBENTRY,
    FakeClock,
    device_subentry,
    make_entry,
    set_lg,
    setup,
)


async def test_diagnostics(hass: HomeAssistant, clock: FakeClock) -> None:
    set_lg(hass, "on", "PC")
    entry = await setup(
        hass, make_entry(device_subentry(LG_SUBENTRY, "LG", LG, mode_exceptions=["pc"]))
    )
    await clock.advance(60)

    diag = await async_get_config_entry_diagnostics(hass, entry)

    lg = diag["devices"][LG_SUBENTRY]
    assert lg["tracker_state"] == "Counting"
    assert lg["raw_app"] == "PC"
    assert lg["resolved_app"] == {"key": "pc", "display_name": "PC"}
    assert lg["default_mode"] == "playing_only"
    assert lg["mode_exceptions"] == ["pc"]
    assert lg["effective_mode"] == "app_open"
    assert lg["grace_period"] == 60
    assert lg["totals"]["pc"]["minutes"] > 0
    assert diag["combined"]["pc"]["minutes"] > 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_diagnostics.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.watch_time_tracker.diagnostics'`.

- [ ] **Step 3: Implement**

`custom_components/watch_time_tracker/diagnostics.py`:
```python
"""Diagnostics for Watch Time Tracker."""

from typing import Any

from homeassistant.core import HomeAssistant

from . import WatchTimeConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: WatchTimeConfigEntry
) -> dict[str, Any]:
    """Return tracker state, app detection and totals per device."""
    runtime = entry.runtime_data
    return {
        "options": dict(entry.options),
        "devices": {
            subentry_id: device.diagnostics()
            for subentry_id, device in runtime.devices.items()
        },
        "combined": runtime.hub.totals,
    }
```

- [ ] **Step 4: Run the tests and lint**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/ruff format --check .`
Expected: `83 passed`, lint clean.

- [ ] **Step 5: Commit**

```bash
git add custom_components/watch_time_tracker/diagnostics.py tests/test_diagnostics.py
git commit -m "feat: add config entry diagnostics"
```

---

### Task 8: Packaging: HACS, README, CI and brand images

**Files:**
- Create: `hacs.json`, `.github/workflows/validate.yml`, `scripts/make_brand.py`
- Create (generated): `custom_components/watch_time_tracker/brand/icon.png`, `icon@2x.png`, `logo.png`, `logo@2x.png`
- Modify: `README.md` (full replacement)

**Interfaces:**
- Consumes: the finished integration.
- Produces: an installable HACS custom repository with CI.

- [ ] **Step 1: Add HACS metadata**

`hacs.json`:
```json
{
  "name": "Watch Time Tracker",
  "homeassistant": "2026.9.0"
}
```

- [ ] **Step 2: Add the CI workflow**

`.github/workflows/validate.yml`:
```yaml
name: Validate

on:
  push:
  pull_request:
  workflow_dispatch:

jobs:
  hacs:
    name: HACS validation
    runs-on: ubuntu-latest
    steps:
      - uses: hacs/action@main
        with:
          category: integration
          ignore: brands

  hassfest:
    name: hassfest
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: home-assistant/actions/hassfest@master

  tests:
    name: Lint and tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
          cache: pip
          cache-dependency-path: requirements_test.txt
      - run: pip install -r requirements_test.txt
      - run: ruff check .
      - run: ruff format --check .
      - run: pytest
```

`ignore: brands` stops the HACS action from requiring an entry in the home-assistant/brands repository. Since HA 2026.3, the local `brand/` folder is used instead.

- [ ] **Step 3: Add the brand image generator and generate the images**

`scripts/make_brand.py`:
```python
"""Generate the brand images in custom_components/watch_time_tracker/brand/.

Run: python scripts/make_brand.py  (needs Pillow, which Home Assistant installs)
"""

from pathlib import Path

from PIL import Image, ImageDraw

BRAND = Path(__file__).parent.parent / "custom_components/watch_time_tracker/brand"
BLUE = (3, 169, 244, 255)
WHITE = (255, 255, 255, 255)


def icon(size: int) -> Image.Image:
    """A TV with a clock on its screen."""
    s = size / 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=48 * s, fill=BLUE)
    # TV body and stand
    d.rounded_rectangle(
        (36 * s, 56 * s, 220 * s, 180 * s),
        radius=14 * s,
        outline=WHITE,
        width=round(12 * s),
    )
    d.line((100 * s, 210 * s, 156 * s, 210 * s), fill=WHITE, width=round(12 * s))
    d.line((128 * s, 180 * s, 128 * s, 210 * s), fill=WHITE, width=round(12 * s))
    # Clock
    d.ellipse((92 * s, 82 * s, 164 * s, 154 * s), outline=WHITE, width=round(9 * s))
    d.line((128 * s, 118 * s, 128 * s, 96 * s), fill=WHITE, width=round(8 * s))
    d.line((128 * s, 118 * s, 146 * s, 118 * s), fill=WHITE, width=round(8 * s))
    return img


def main() -> None:
    BRAND.mkdir(parents=True, exist_ok=True)
    for name, size in (("icon.png", 256), ("icon@2x.png", 512)):
        icon(size).save(BRAND / name)
    # Logo: same mark (HA falls back to the icon shape for square logos).
    icon(256).save(BRAND / "logo.png")
    icon(512).save(BRAND / "logo@2x.png")


if __name__ == "__main__":
    main()
```

Run: `.venv/bin/python scripts/make_brand.py && ls custom_components/watch_time_tracker/brand`
Expected: `icon.png  icon@2x.png  logo.png  logo@2x.png`. The image is a white TV outline with a clock on a rounded blue (#03A9F4) square. Open `icon@2x.png` and check it looks right.

- [ ] **Step 4: Write the README**

Replace `README.md`:
````markdown
# Watch Time Tracker

A Home Assistant custom integration that tracks how long each app or source is watched on your TVs. You get a running watch-time total per source for every TV, plus a combined total per source over all TVs.

## Installation

### HACS (custom repository)

1. In HACS, open the menu (⋮) → **Custom repositories**.
2. Add `https://github.com/jelle514/WatchTimeTracker` with type **Integration**.
3. Install **Watch Time Tracker** and restart Home Assistant.

### Manual

Copy `custom_components/watch_time_tracker` into your Home Assistant `config/custom_components/` folder and restart.

## Setup

1. **Settings → Devices & services → Add integration → Watch Time Tracker.**
2. On the Watch Time Tracker entry, choose **Add tracked TV** for each TV:
   - **Media player**: the TV's media player entity. Its state decides playing, on or off.
   - **Extra activity entity** (optional): a remote or media player that names the current app when the media player doesn't, or says `playing` when the media player can't. The TV counts as playing when either entity says `playing`; the media player alone decides whether the TV is on. See the example setups below.
   - **Default counting mode** and **grace period**: see below.
3. On the next screen, **Counting mode per source**, pick the sources on this TV that use the other counting mode.

Each TV gets an **Activity** sensor and a **watch time** sensor per source. The **All TVs** device has the combined watch time sensors. Totals are stored in minutes and shown in hours with one decimal.

## Example setups

**LG webOS TV with Chromecast built in**
- Media player: the LG webOS entity.
- Extra activity entity: the TV's Google Cast entity. While you cast, the LG says `playing` without naming the app; the Cast entity names it.
- Counting mode per source: tick the HDMI inputs (PC, game consoles). They report `on`, never `playing`.

**Chromecast with Google TV**
- Media player: the Android TV Remote media player. It knows on/off and the app (as a package name, mapped to a friendly name), but never says `playing`.
- Extra activity entity: the Google Cast entity. It says `playing` during playback and is `off` on the home screen.
- Netflix reports `playing` as soon as it is open, so browsing Netflix counts as Netflix watch time. No entity reports anything better.

## Counting modes

- **Only while playing** (default): time counts while the media player is `playing`. This is the most accurate for apps that report playback, such as YouTube and Netflix.
- **Whenever an app is open**: time counts whenever the TV is on with the source open, whatever the playback state.

Sources that never report `playing` need the second mode. On LG webOS TVs this is typically every **HDMI input** (PC, game consoles). Leave the TV's default on *Only while playing* and pick those sources on the **Counting mode per source** screen. The choice is per TV, because TVs report states differently: the same app can count only while playing on one TV and whenever it's open on another.

Time while the app can't be identified is counted as **Unknown app**, but only while the TV reports `playing`, whatever the TV's default mode. That keeps home screens from being counted.

## Grace period

Short gaps count as watching: the moment between two videos, a brief pause, a short network drop. A gap longer than the grace period (default 60 s) isn't counted, and the session ends at the start of the gap. Set it to 0 to count only uninterrupted playback.

## App name mapping

Raw app values (like `com.netflix.ninja`) are turned into display names by a built-in table. You can override it under **Configure** on the main entry, one line per value:

```
com.netflix.ninja = Netflix
PC = Gaming PC
com.google.android.apps.tv.launcherx = !ignore
```

`!ignore` means the value is never counted, which is useful for home screens and launchers. Matching is case-insensitive.

Changing a mapping after time has been counted starts a new sensor. The old sensor keeps its total and stops growing. Re-pick the source on the **Counting mode per source** screen if it used the other mode.

## Removing a TV

Deleting a tracked TV removes its device, sensors and per-TV totals. The combined totals keep the time it contributed.
````

- [ ] **Step 5: Full verification**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/ruff format --check . && python3 -c "import json; json.load(open('hacs.json')); json.load(open('custom_components/watch_time_tracker/manifest.json')); json.load(open('custom_components/watch_time_tracker/translations/en.json'))"`
Expected: `83 passed`, lint clean, no JSON errors.

- [ ] **Step 6: Commit and check CI**

```bash
git add hacs.json .github scripts README.md custom_components/watch_time_tracker/brand
git commit -m "build: add HACS metadata, CI, README and brand images"
```

After pushing (ask the owner before pushing), check that all three CI jobs pass: `gh run list --limit 1` then `gh run view <id>`. If hassfest reports a translation or manifest schema error, fix it exactly as reported. It validates against the latest HA, which may be newer than 2026.9.

---

### Task 9: Apply the real-TV findings

Uses `docs/superpowers/device-check.md` from Task 0.

**Files:**
- Modify: `custom_components/watch_time_tracker/app_names.py` (`BUILTIN_NAMES`)
- Modify: `custom_components/watch_time_tracker/const.py` (`DEFAULT_GRACE_PERIOD`, only if needed)
- Modify: `README.md` (only if findings change the advice)
- Test: `tests/test_app_names.py` (one lookup test per new table entry)

- [ ] **Step 1: Re-read the notes**

Read `docs/superpowers/device-check.md`. If it's missing situations from Task 0, ask the owner to complete it first.

- [ ] **Step 2: Apply the findings**

- Add every raw value that isn't already a friendly name to `BUILTIN_NAMES` (casefolded key → display name), e.g. `"f1tv chromecast": "F1 TV"` if the owner wants that name. Add launcher/home-screen values with `None`. Add a `test_builtin_lookup`-style test for each one.
- If the LG reports `source` for native apps and the Cast entity is `off`/`idle` meanwhile, the detection order stands. If the Cast entity keeps a stale `app_name` while a native app runs, nothing breaks (the LG's `source` wins), but note it in the README.
- If the Cast entity doesn't report `playing` for an app, note in the README that that app goes in the Slaapkamer TV's per-source list. If most apps don't, recommend "Whenever an app is open" as that TV's default.
- If HDMI sources report `on` (expected), the README's HDMI advice stands. If they report `playing`, remove that advice.
- If the measured gap between videos is longer than 60 s, raise `DEFAULT_GRACE_PERIOD` in `const.py` to cover it.

- [ ] **Step 3: Run the tests and commit**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/ruff format --check .`
Expected: all tests pass, lint clean.

```bash
git add -A custom_components tests README.md
git commit -m "feat: update built-in app names from real-device check"
```

---

## Spec coverage

| Spec section | Task |
|---|---|
| Packaging and distribution (manifest, hacs.json, translations, brand, CI, README) | 1, 8 |
| Main entry, options flow with `!ignore` and line errors | 1, 6 |
| Sub-entry fields, "Counting mode per source" step, labels following the default mode, per-TV lists, duplicate check, reconfigure | 6 |
| Lifecycle of changes (reload listener, unload closes sessions, stale data cleanup) | 4, 5 |
| App detection order, name mapping, ignored values, source keys and hash fallback, built-in table | 2, 9 |
| Name mapping changes (new sensor, re-pick per-source mode) | README in 8 (behaviour is inherent to keys) |
| Devices and entities, unique IDs, sub-entry linking, sensor properties, dynamic creation, entity conventions | 4 |
| Combined totals with their own count; removing a TV keeps combined | 4, 5 |
| Situation and per-source mode, state machine, grace 0, live tick, monotonic time, negative guard | 3, 4 |
| Timers and listeners, `runtime_data` | 4, 5 |
| Persistence (Store with version/minor/migration, delayed save, save on stop/unload, load before tracking) | 4, 5 |
| Edge cases (unavailable via grace, missing entity, source not in `source_list`) | 3, 4 |
| Diagnostics | 7 |
| Before implementation | 0 (record), 9 (apply) |
