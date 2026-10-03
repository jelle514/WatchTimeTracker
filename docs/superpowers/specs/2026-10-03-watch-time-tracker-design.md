# Watch Time Tracker — Design

**Date:** 2026-10-03
**Status:** Approved design, pending implementation plan
**Supersedes:** `lg-webos-source-tracker-brief.md` (single LG TV scope)

## Goal

A Home Assistant custom integration that tracks how long each source/app is watched on one or more TVs (media player entities). It produces a running watch-time total per source per TV, plus a combined total per source across all TVs. It is installable through HACS as a custom repository.

## Context

- Home Assistant 2026.9.4, time zone Europe/Amsterdam.
- **Woonkamer TV** (LG webOS): `media_player.lg_webos_smart_tv`. Reports `source` and `source_list` (Disney+, HDMI 4, NPO Start, Netflix, Nintendo Switch Game Console, PC, Plex, Sonos Beam, YouTube). Two stale duplicates exist (`media_player.lg_webos_tv_oled55c34la`, `..._2`) that should not be used.
- **Slaapkamer TV** (Chromecast with Google TV): `media_player.chromecast` (Google Cast), `media_player.slaapkamer_tv_2` (Android TV Remote, `assumed_state`), `remote.slaapkamer_tv` (Android TV Remote, `current_activity`). It has no `source_list`.
- The existing `sensor.tv_active_source` template helper references `media_player.lg_webos_tv`, which does not exist. It therefore always reports `idle`. The integration replaces it.
- Known LG behaviour: YouTube flips between `playing` and `paused` every 20–60 seconds during playback, which undercounts without a grace period.

## Decisions

| Topic | Decision |
|---|---|
| Configuration structure | One main config entry, with one config sub-entry per tracked TV |
| Combined totals | Sum of the per-device time (YouTube for 1 h on two TVs = 2 h combined) |
| Combined activity sensor | Not included |
| What counts as watching | Configurable per device: "playing only" or "any on-state with app open" |
| Sensor type | Running totals, `total_increasing`. Period sensors may be spin-offs later |
| Unit | Native unit is minutes, stored as a float and never rounded during accumulation. Suggested display unit is hours |
| App name normalisation | A built-in mapping that user overrides take priority over |
| Distribution | HACS custom repository and manual copy |

## Packaging and distribution

```
hacs.json
README.md
custom_components/watch_time_tracker/
  manifest.json
  __init__.py
  app_names.py
  config_flow.py
  const.py
  device.py
  hub.py
  sensor.py
  storage.py
  strings.json
  translations/en.json
.github/workflows/validate.yml
tests/
```

- **Domain:** `watch_time_tracker`. **Name:** Watch Time Tracker.
- **`hacs.json`:** `name` and `homeassistant: "2026.9.0"` (the version tested against; lowered only after testing on older releases). `render_readme: true`.
- **`manifest.json`:** `domain`, `name`, `version`, `config_flow: true`, `single_config_entry: true`, `integration_type: "hub"`, `iot_class: "calculated"`, `documentation`, `issue_tracker`, `codeowners`, `requirements: []`, and `dependencies` as needed.
- **Releases:** every version is a GitHub release whose tag matches `manifest.json`'s `version`, so HACS offers updates.
- **CI:** a GitHub Actions workflow running the HACS validation action, `hassfest` and pytest on push and pull request.
- **README:** covers installation (HACS custom repository and manual copy), setup steps, an explanation of the counting modes and grace period, and the name mapping format.

## Configuration

### Main entry

- Single instance. The setup flow has no fields and only creates the entry.
- **Options flow:** a multi-line text field for app name overrides, one `raw value = Display Name` per line. Invalid lines are rejected with an error that names the line.
- Owns the combined device and its sensors.

### Sub-entry: tracked device ("Add tracked device")

| Field | Required | Default | Notes |
|---|---|---|---|
| Name | yes | media player's friendly name | Device name |
| Media player | yes | — | Entity selector, `media_player` domain. Its state decides playing, on or off |
| Extra activity entity | no | — | Entity selector (`remote`, `media_player`). Used when the media player doesn't identify the app |
| Counting mode | yes | Playing only | `playing_only` or `app_open` |
| Grace period | yes | 60 s | 0–600 s |

- The same media player cannot be tracked by two sub-entries; the flow aborts with an error.
- A reconfigure flow can change every field. Changing the media player keeps the device's totals.

### App detection

The raw app value is the first non-empty value of:

1. the media player's `source` attribute
2. the media player's `app_name` attribute
3. the extra entity's `current_activity` attribute
4. the extra entity's `source` attribute
5. the extra entity's `app_name` attribute

The raw value is resolved through the name mapping. User overrides are checked first, then the built-in table, then the raw value is used unchanged. The resolved display name gives the **source key** (`slugify(display_name)`, e.g. `youtube`). Matching keys share a combined sensor.

The built-in table starts with common Google TV / Android TV package names (YouTube, Netflix, Disney+, Plex, NPO Start, Prime Video, Spotify). It is updated with the values recorded during the Chromecast check (see "Before implementation").

## Devices and entities

### Per tracked TV (device = sub-entry)

| Entity | Unique ID | State |
|---|---|---|
| Activity | `{subentry_id}_activity` | The display name while counting (including during the grace period), `idle` when on but not counting, `off` when off/unavailable, `unknown` when on/playing but the app can't be identified |
| Watch time for each source | `{subentry_id}_{source_key}` | Running total in minutes |

### Combined (device owned by the main entry)

| Entity | Unique ID | State |
|---|---|---|
| Watch time for each source | `combined_{source_key}` | Running total in minutes |

### Watch time sensor properties

- `device_class: duration`, `state_class: total_increasing`, native unit `min`, suggested unit `h`, float value.
- **Created dynamically:**
  - From `source_list` when a device is set up and whenever `source_list` changes.
  - On the first counted session for a source key with no sensor yet.
  - From the saved list of known sources at startup, so sensors exist even while the TV is off.
- A combined sensor is created when any device creates its first sensor for that source key.
- Entity names use the display name, e.g. "YouTube watch time" on the device "Slaapkamer TV".

### Combined totals

The combined sensors keep **their own count** and do not compute a live sum. Every amount of time a device earns is added to the device sensor and to the matching combined sensor at the same moment. As a result, removing a tracked TV never lowers a combined total, which `total_increasing` would read as a meter reset.

### Removing a tracked TV

Removing a sub-entry deletes its device, its entities and its saved per-device totals. Combined totals keep the time it contributed.

## How time is counted

### Situation

At every state change of the media player or the extra entity, the device works out its situation:

- **Counting(app)** when an app is known and:
  - mode `playing_only`: the media player's state is `playing`
  - mode `app_open`: the media player's state is not one of `off`, `unavailable`, `unknown`, `standby`
- **NotCounting** otherwise.

### State machine (`tracker.py`)

States: `Idle`, `Counting(app, since)`, `Grace(app, since, gap_start)`.

| From | Event | To | Effect |
|---|---|---|---|
| Idle | Counting(app) | Counting(app, now) | — |
| Counting(app) | NotCounting | Grace(app, since, now) | Start grace timer |
| Counting(app) | Counting(other) | Counting(other, now) | Credit `app` with `now − since` |
| Grace(app) | Counting(app) | Counting(app, since) | Cancel timer; the gap counts as watching |
| Grace(app) | Counting(other) | Counting(other, now) | Credit `app` with `gap_start − since`; the gap is not counted |
| Grace(app) | Grace timer expires | Idle | Credit `app` with `gap_start − since` |
| Counting(app) | Live update tick | Counting(app, now) | Credit `app` with `now − since` |
| any | Shutdown | Idle | Close any open session as above (Grace credits up to `gap_start`) |

- A grace period of 0 s closes the session straight away.
- The **live update tick** runs every 60 s while in `Counting`. Time already credited by a tick is not credited again: `since` moves forward to the tick time. While in `Grace`, ticks credit nothing.
- If a time difference is negative (clock jump), nothing is credited.
- `tracker.py` is a plain Python class with no Home Assistant imports. Time is passed in as an argument. It returns a list of `(source_key, minutes)` credits.

### Persistence

- `storage.py` wraps `homeassistant.helpers.storage.Store` (versioned). It saves:
  - per sub-entry: `{source_key: {display_name, minutes}}`
  - combined: `{source_key: {display_name, minutes}}`
- Every credit triggers a delayed save (`async_delay_save`, ~30 s).
- The sensors also implement `RestoreSensor`. If storage is missing or corrupt, the last restored state is used as the starting total.
- **Shutdown** (`EVENT_HOMEASSISTANT_STOP` / entry unload): close open sessions and save immediately.
- **Startup:** totals come from storage, and the situation is read from the current entity states. Downtime is never credited.

### Edge cases

- `unavailable` is NotCounting. It goes through the grace period like any other gap, so a short network drop doesn't split a session.
- A tracked entity that doesn't exist (yet) gives NotCounting. Setup does not fail.
- A source key that isn't in `source_list` is still tracked.

## Code structure

| File | Job | Depends on |
|---|---|---|
| `const.py` | Domain, config keys, defaults | — |
| `app_names.py` | Built-in table, override parsing, `resolve(raw, overrides) -> (key, display_name)` | — |
| `tracker.py` | The state machine above | — |
| `storage.py` | Load and save totals | HA `Store` |
| `hub.py` | Combined totals; receives credits from devices; announces new combined sources | `storage.py` |
| `device.py` | One per sub-entry: subscribes to entity state changes, works out the situation, runs the grace timer and live tick, feeds `tracker.py`, passes credits to its sensors and the hub, announces new sources | `tracker.py`, `app_names.py`, `hub.py`, `storage.py` |
| `sensor.py` | Activity, per-device and combined watch time entities; adds entities on new-source signals (dispatcher) | `device.py`, `hub.py` |
| `config_flow.py` | Main flow, options flow, sub-entry flow and reconfigure | — |
| `__init__.py` | Entry setup and unload, sub-entry lifecycle | all |

## Testing

- **Unit tests (no HA):**
  - `app_names`: built-in lookups, override priority, override parsing errors, unknown values, slug keys.
  - `tracker` with a fake clock:
    - flapping shorter than the grace period is fully counted
    - a gap longer than the grace period is not counted
    - switching apps during the grace period
    - both counting modes
    - a grace period of 0
    - live ticks don't double-count
    - negative time differences
    - shutdown during `Counting` and during `Grace`
- **Integration tests** (`pytest-homeassistant-custom-component`):
  - main flow, single-instance abort, options validation
  - sub-entry create, duplicate media player abort, reconfigure
  - sensors created from `source_list` and on first sight
  - activity sensor states
  - credits reach the device and combined sensors
  - totals survive a restart (storage and restore fallback)
  - removing a sub-entry keeps the combined totals
- **CI:** HACS validation, hassfest, pytest.

## Before implementation

Turn on the Slaapkamer TV and open the commonly used apps (at least YouTube, Netflix, Plex, Disney+). For each app, record from the HA REST API:

- `media_player.chromecast`: state, `app_name`, `app_id`, other media attributes
- `remote.slaapkamer_tv`: state, `current_activity`
- `media_player.slaapkamer_tv_2`: state

Do the same for the LG during YouTube playback to confirm the flapping. Use the results to:

- confirm or adjust the app detection order
- fill the built-in name table with the real values
- confirm that the Cast entity reports `playing` for native apps. If it doesn't, the Slaapkamer TV needs `app_open` mode, and the README should say so.

## Out of scope

- Daily/weekly/monthly sensors (possible spin-offs later, on top of `total_increasing` statistics)
- Combined activity sensor
- Overlap-aware combined totals
- Crediting time while HA was down
