# Watch Time Tracker — Design

**Date:** 2026-10-03 (revised 2026-10-04 after review)
**Status:** Approved design, pending implementation plan
**Supersedes:** `lg-webos-source-tracker-brief.md` (single LG TV scope)

## Goal

A Home Assistant custom integration that tracks how long each source/app is watched on one or more TVs (media player entities). It produces a running watch-time total per source per TV, plus a combined total per source across all TVs. It is installable through HACS as a custom repository.

## Context

- Home Assistant 2026.9.4, time zone Europe/Amsterdam.
- **Woonkamer TV** (LG webOS): `media_player.lg_webos_smart_tv`. Reports `source` and `source_list` (Disney+, HDMI 4, NPO Start, Netflix, Nintendo Switch Game Console, PC, Plex, Sonos Beam, YouTube). `media_player.lg_webos_tv_oled55c34la` is a stale duplicate (unavailable) and should not be used. `media_player.lg_webos_tv_oled55c34la_2` is the LG's **built-in Chromecast** (Google Cast) and is the LG's extra activity entity.
- **Slaapkamer TV** (Chromecast with Google TV): `media_player.chromecast` (Google Cast), `media_player.slaapkamer_tv_2` (Android TV Remote, `assumed_state`), `remote.slaapkamer_tv` (Android TV Remote, `current_activity`). It has no `source_list`. Observed 2026-10-04: `slaapkamer_tv_2` reports `on`/`off` and the app as a package name (e.g. `com.google.android.youtube.tv`) but never `playing`; `chromecast` reports `playing` with a friendly `app_name` during YouTube playback and is `off` on the home screen; for Netflix it reports `playing` as soon as the app is open. Setup: media player `slaapkamer_tv_2`, extra activity entity `chromecast`.
- The existing `sensor.tv_active_source` template helper references `media_player.lg_webos_tv`, which does not exist. It therefore always reports `idle`. The integration replaces it.
- Playback has short gaps that would undercount without a grace period: the moment between back-to-back videos (e.g. several short YouTube videos in a row), brief pauses, and short network drops. An earlier observation of YouTube "flipping" between `playing` and `paused` turned out to be this, not an app bug.
- Observed 2026-10-04 while casting F1 TV to the LG: the LG entity reports `playing` with `source_list` but **no `source` attribute**. The built-in Chromecast entity reports `playing` with `app_name: F1TV Chromecast` and `app_id: B3E81094`. App detection therefore falls back to the extra entity's `app_name`; without the extra entity, casting would count as "Unknown app".
- HDMI inputs (PC, Nintendo Switch, HDMI 4) have no media session. Confirmed 2026-10-04 on the PC input: the LG reports `on` with `source: PC` (the built-in Chromecast is `off`), so `playing_only` mode would never count them. Apps that do report `playing` should still be counted only while playing, which is why the counting mode can be set per source.

## Decisions

| Topic | Decision |
|---|---|
| Configuration structure | One main config entry, with one config sub-entry per tracked TV |
| Combined totals | Sum of the per-device time (YouTube for 1 h on two TVs = 2 h combined) |
| Combined activity sensor | Not included |
| What counts as watching | Per source: "playing only" or "while open". Each TV has a default mode and a manual list of sources that use the other mode |
| Sensor type | Running totals, `total_increasing`. Period sensors may be spin-offs later |
| Unit | Native unit is minutes, stored as a float and never rounded during accumulation. Displayed in hours with 1 decimal by default |
| App name normalisation | A built-in mapping that user overrides take priority over. Raw values can be marked as ignored |
| Unidentified apps | Time while the app can't be identified goes to an "Unknown app" source instead of being lost, but only while the TV reports `playing`, whatever its default mode (a home screen looks the same as an unknown app) |
| Persistence | `Store` is the only source of truth (no `RestoreSensor`) |
| Durations | Measured with a monotonic clock, not wall-clock time |
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
  diagnostics.py
  hub.py
  sensor.py
  storage.py
  tracker.py
  translations/en.json
  brand/
    icon.png
    logo.png
.github/workflows/validate.yml
tests/
```

- **Domain:** `watch_time_tracker`. **Name:** Watch Time Tracker.
- **`hacs.json`:** `name` and `homeassistant: "2026.9.0"` (the version tested against; lowered only after testing on older releases). No `render_readme`: HACS 2.x always shows the README.
- **`manifest.json`:** `domain`, `name`, `version`, `config_flow: true`, `single_config_entry: true`, `integration_type: "hub"`, `iot_class: "calculated"`, `documentation`, `issue_tracker`, `codeowners`, `requirements: []`, and `dependencies` as needed.
- **Translations:** only `translations/en.json`. No `strings.json` (that is a core-repo convention).
- **Brand images:** shipped in `brand/` inside the integration (supported since HA 2026.3). The HACS validation action may still need `ignore: brands`.
- **Releases:** every version is a GitHub release whose tag matches `manifest.json`'s `version`, so HACS offers updates.
- **CI:** a GitHub Actions workflow running the HACS validation action, `hassfest` and pytest on push and pull request.
- **README:** covers installation (HACS custom repository and manual copy), setup steps, an explanation of the counting modes (including the per-source list and which sources typically need it, such as HDMI inputs) and grace period, the name mapping format (including ignored values), and the fact that changing a name override starts a new sensor (see "Name mapping changes").

## Configuration

### Main entry

- Single instance. The setup flow has no fields and only creates the entry.
- **Options flow:** a multi-line text field for app name overrides, one line per value:
  - `raw value = Display Name` maps a raw value to a display name.
  - `raw value = !ignore` marks a raw value as ignored (e.g. a home screen launcher).
  - Invalid lines are rejected with an error that names the line.
- Owns the combined device and its sensors.

### Sub-entry: tracked device ("Add tracked device")

| Field | Required | Default | Notes |
|---|---|---|---|
| Name | yes | media player's friendly name | Device name and sub-entry title |
| Media player | yes | — | Entity selector, `media_player` domain. Its state decides playing, on or off |
| Extra activity entity | no | — | Entity selector (`remote`, `media_player`). Names the app when the media player doesn't, and can supply `playing` (see "Situation") |
| Default counting mode | yes | Playing only | `playing_only` or `app_open` |
| Grace period | yes | 60 s | 0–600 s |

The flow has a second step, **"Counting mode per source"**:

| Field | Required | Default | Notes |
|---|---|---|---|
| Sources that use the other mode | no | empty | Multi-select. The label follows the default mode: "Sources that count whenever they're open" (default `playing_only`) or "Sources that count only while playing" (default `app_open`) |

- The options are the display names from the media player's current `source_list` plus the sources already known for this device (stored totals). Custom values can be typed, for apps that haven't been seen yet.
- Selections are stored as source keys (resolved through the name mapping), so they match whatever raw value the TV reports.
- The default mode and the list belong to this TV only, because TVs report states differently. The same source can use a different mode on another TV (e.g. Plex counts only while playing on the LG, but whenever it's open on the Chromecast).
- "Unknown app" always counts only while playing, whatever the default mode, and can't be put in the list.
- The reconfigure flow has the same two steps.
- When reconfigure changes the default mode, the list is cleared (its entries would mean the opposite) and the sources step says so.

- The same media player cannot be tracked by two sub-entries; the flow aborts with an error. This is checked in both the create and the reconfigure flow.
- A reconfigure flow can change every field. Changing the media player keeps the device's totals.

### Lifecycle of changes

- The main entry has an update listener that reloads the entry whenever sub-entries are added, changed or removed, or the options change.
- Unloading closes all open sessions (as on shutdown) and saves immediately.
- On setup, stored per-device data whose sub-entry ID no longer exists is deleted. Combined totals are kept.

### App detection

The raw app candidates are the non-empty values of, in this order:

1. the media player's `source` attribute
2. the media player's `app_name` attribute
3. the extra entity's `current_activity` attribute
4. the extra entity's `source` attribute
5. the extra entity's `app_name` attribute

Each candidate is resolved through the name mapping: user overrides first, then the built-in table, then the raw value unchanged. The **first candidate that isn't ignored** is the app. Ignored candidates are skipped, so a Cast receiver package on the media player (`com.google.android.apps.mediashell`, observed while casting F1 TV to the Slaapkamer TV) falls through to the Cast entity's friendly `app_name`. If every candidate is ignored (e.g. a home screen launcher), the device is NotCounting, whatever the counting mode. If there are no candidates at all, the app is "Unknown app".

The resolved display name gives the **source key**: `slugify(display_name)`, e.g. `youtube`. If the slug is empty (e.g. emoji-only or some non-Latin names), the key is `app_` plus the first 8 hex characters of the SHA-1 of the display name. Display names that give the same slug (e.g. `Disney+` and `Disney`) share one sensor; this is intended. Matching keys share a combined sensor.

The built-in table starts with common Google TV / Android TV package names (YouTube, Netflix, Disney+, Plex, NPO Start, Prime Video, Spotify) and marks known launchers (e.g. the Google TV home screen) and the Google TV Cast receiver (`com.google.android.apps.mediashell`) as ignored. It is updated with the values recorded during the Chromecast check (see "Before implementation").

### Name mapping changes

Changing an override after time has been counted changes the source key. The old sensor keeps its total and stops growing, and a new sensor starts at 0. A per-source counting mode selection for the old key no longer applies and has to be set again for the new one. Merging totals is out of scope.

## Devices and entities

### Per tracked TV (device = sub-entry)

| Entity | Unique ID | State |
|---|---|---|
| Activity | `{subentry_id}_activity` | The display name while counting (including during the grace period; "Unknown app" when the app can't be identified), `idle` when on but not counting, `off` when off/unavailable. It never uses a literal `"unknown"` string, which would clash with HA's own `unknown` state |
| Watch time for each source | `{subentry_id}_watch_{source_key}` | Running total in minutes |

- The device is registered with `config_subentry_id`, and its entities are added with `async_add_entities(..., config_subentry_id=subentry_id)`. This puts them under the right sub-entry in the UI and lets HA remove them when the sub-entry is removed.

### Combined (device owned by the main entry)

| Entity | Unique ID | State |
|---|---|---|
| Watch time for each source | `combined_watch_{source_key}` | Running total in minutes |

### Watch time sensor properties

- `device_class: duration`, `state_class: total_increasing`, native unit `min`, float value.
- `suggested_unit_of_measurement: h` and `suggested_display_precision: 1`, so totals display as e.g. `3.3 h`.
- **Created dynamically:**
  - From `source_list` when a device is set up and whenever `source_list` changes.
  - On the first counted session for a source key with no sensor yet.
  - From the saved list of known sources at startup, so sensors exist even while the TV is off.
- A combined sensor is created when any device creates its first sensor for that source key.

### Entity conventions

- `_attr_has_entity_name = True`, `_attr_should_poll = False`.
- Names come from `translation_key` with placeholders, e.g. `"{app} watch time"`, giving "YouTube watch time" on the device "Slaapkamer TV".
- The "Unknown app" source uses the source key `unknown_app`.

### Combined totals

The combined sensors keep **their own count** and do not compute a live sum. Every amount of time a device earns is added to the device sensor and to the matching combined sensor at the same moment. As a result, removing a tracked TV never lowers a combined total, which `total_increasing` would read as a meter reset.

### Removing a tracked TV

Removing a sub-entry deletes its device and its entities (through the `config_subentry_id` link) and its saved per-device totals (on the reload that follows, see "Lifecycle of changes"). Combined totals keep the time it contributed.

## How time is counted

### Situation

At every state change of the media player or the extra entity, the device works out its situation.

First the **player state**: the media player's state, except that it becomes `playing` when the media player is on (not `off`, `unavailable`, `unknown`, `standby`, or missing) and the extra entity's state is `playing` **for the same app**: the extra entity's own app (detected from its attributes alone) is the detected app, or it names no app. The media player alone decides on/off; either entity can say it is playing. The same-app condition exists because a cast session left open on a phone kept the Cast entity on F1 TV while Disney+ was on screen (observed 2026-10-04). This is needed for a Chromecast with Google TV, whose Android TV Remote player never says `playing` while its Cast entity does.

Then:

- **Counting(app)** when the app is not ignored and the device is active for that app's counting mode:
  - `playing_only`: the player state is `playing`
  - `app_open`: the player state is not one of `off`, `unavailable`, `unknown`, `standby`

  The app is detected first, then its mode is looked up: the opposite of the default if the app's source key is in the per-source list, otherwise the default. If no app can be identified, `app` is "Unknown app" and it counts only while `playing`, whatever the default mode. On the LG the home screen reports `on` with no `source`, which looks exactly like an unknown app, so this keeps home-screen time out of the totals even with an `app_open` default.
- **NotCounting** otherwise.

### State machine (`tracker.py`)

States: `Idle`, `Counting(app, since)`, `Grace(app, since, gap_start)`.

| From | Event | To | Effect |
|---|---|---|---|
| Idle | Counting(app) | Counting(app, now) | — |
| Idle | NotCounting | Idle | — |
| Counting(app) | Counting(app) | Counting(app, since) | — (e.g. an attribute changed, same app) |
| Counting(app) | NotCounting | Grace(app, since, now) | Start grace timer |
| Counting(app) | Counting(other) | Counting(other, now) | Credit `app` with `now − since` |
| Grace(app) | NotCounting | Grace(app, since, gap_start) | — (e.g. `paused` → `off`; the timer keeps running) |
| Grace(app) | Counting(app) | Counting(app, since) | Cancel timer; the gap counts as watching |
| Grace(app) | Counting(other) | Counting(other, now) | Credit `app` with `gap_start − since`; the gap is not counted |
| Grace(app) | Grace timer expires | Idle | Credit `app` with `gap_start − since` |
| Counting(app) | Live update tick | Counting(app, now) | Credit `app` with `now − since` |
| any | Shutdown / unload | Idle | Close any open session as above (Grace credits up to `gap_start`) |

- A grace period of 0 s closes the session straight away.
- The **live update tick** runs every 60 s while in `Counting`. Time already credited by a tick is not credited again: `since` moves forward to the tick time. While in `Grace`, ticks credit nothing.
- Times are monotonic (`time.monotonic()`), so wall-clock changes don't affect durations. A negative difference is still guarded against and credits nothing.
- `tracker.py` is a plain Python class with no Home Assistant imports. Time is passed in as an argument. It returns a list of `(source_key, minutes)` credits.

### Timers and listeners

- Entity changes: `async_track_state_change_event` on the media player and the extra entity.
- Grace timer: `async_call_later`.
- Live tick: `async_track_time_interval`, started on entering `Counting` and stopped on leaving it.
- Every listener and timer is cancelled through `entry.async_on_unload`.
- The hub and devices are kept in `entry.runtime_data`, not `hass.data`.

### Persistence

- `storage.py` wraps `homeassistant.helpers.storage.Store` with `version`, `minor_version` and a migration function. It saves:
  - per sub-entry: `{source_key: {display_name, minutes}}`
  - combined: `{source_key: {display_name, minutes}}`
- `Store` is the only source of truth. Sensors do not use `RestoreSensor`.
- Every credit triggers a delayed save (`async_delay_save`, ~30 s).
- **Shutdown** (`EVENT_HOMEASSISTANT_STOP`) and **unload**: close open sessions and save immediately.
- **Startup:** totals are loaded from storage before any tracking starts, and the situation is read from the current entity states. Downtime is never credited.

### Edge cases

- `unavailable` is NotCounting. It goes through the grace period like any other gap, so a short network drop doesn't split a session.
- A tracked entity that doesn't exist (yet) gives NotCounting. Setup does not fail.
- A source key that isn't in `source_list` is still tracked.

## Diagnostics

`diagnostics.py` implements config entry diagnostics with, per device: the current state machine state, the raw detected app value and how it was resolved, the default counting mode, the per-source list, the effective mode of the current app, the grace period, and the stored totals. Combined totals are included too.

## Code structure

| File | Job | Depends on |
|---|---|---|
| `const.py` | Domain, config keys, defaults | — |
| `app_names.py` | Built-in table, override parsing, `resolve(raw, overrides)`, `detect_app(media_attrs, extra_attrs, overrides)` (first non-ignored candidate) | — |
| `tracker.py` | The state machine above | — |
| `storage.py` | Load, save and migrate totals | HA `Store` |
| `hub.py` | Combined totals; receives credits from devices; announces new combined sources | `storage.py` |
| `device.py` | One per sub-entry: subscribes to entity state changes, works out the situation, runs the grace timer and live tick, feeds `tracker.py`, passes credits to its sensors and the hub, announces new sources | `tracker.py`, `app_names.py`, `hub.py`, `storage.py` |
| `sensor.py` | Activity, per-device and combined watch time entities; adds entities on new-source signals (dispatcher) | `device.py`, `hub.py` |
| `diagnostics.py` | Config entry diagnostics | `hub.py`, `device.py` |
| `config_flow.py` | Main flow, options flow, sub-entry flow and reconfigure | `app_names.py` |
| `__init__.py` | Entry setup and unload, update listener, sub-entry lifecycle, stale data cleanup | all |

## Testing

- **Unit tests (no HA):**
  - `app_names`: built-in lookups, override priority, override parsing errors, `!ignore`, unknown values, slug keys, empty-slug hash fallback, detection order, skipping ignored candidates, all candidates ignored, no candidates.
  - `tracker` with a fake clock:
    - short gaps (between videos, brief pauses) shorter than the grace period are fully counted
    - a gap longer than the grace period is not counted
    - switching apps during the grace period
    - `off` during the grace period
    - same-app updates are no-ops
    - both counting modes
    - per-source mode: an HDMI source counts while `on` and an app on the same TV counts only while `playing`
    - switching between sources with different modes
    - "Unknown app" counts only while playing, even with an `app_open` default
    - player state: the extra entity's `playing` counts when the media player is on and the extra entity names no app or the same app; the media player being off always wins
    - a grace period of 0
    - live ticks don't double-count
    - negative time differences
    - shutdown during `Counting` and during `Grace`
- **Integration tests** (`pytest-homeassistant-custom-component`, pinned to the version matching HA 2026.9):
  - main flow, single-instance abort, options validation
  - sub-entry create, duplicate media player abort (create and reconfigure), reconfigure
  - entities and device linked to the sub-entry
  - sensors created from `source_list` and on first sight
  - activity sensor states, including "Unknown app"
  - ignored apps are not counted in either mode
  - per-source step: options from `source_list` and stored sources, custom values, labels follow the default mode, selections stored as source keys
  - unidentified apps are credited to "Unknown app" while playing
  - the home screen (`on`, no source) is not counted with an `app_open` default
  - Google TV setup (Android TV Remote player + Cast entity): playing YouTube is counted, the home screen is not, a cast app without a Google TV app is named by the Cast entity, a stale cast session for another app is ignored
  - credits reach the device and combined sensors
  - totals survive a restart
  - removing a sub-entry removes its entities and stored data and keeps the combined totals
  - diagnostics output
- **CI:** HACS validation, hassfest, pytest.

## Before implementation

Turn on the Slaapkamer TV and open the commonly used apps (at least YouTube, Netflix, Plex, Disney+), plus the home screen. For each, record from the HA REST API:

- `media_player.chromecast`: state, `app_name`, `app_id`, other media attributes
- `remote.slaapkamer_tv`: state, `current_activity`
- `media_player.slaapkamer_tv_2`: state

Do the same for the LG, including `media_player.lg_webos_tv_oled55c34la_2` (built-in Chromecast):

- while casting from a phone (done 2026-10-04, see Context).
- while a native app plays (does the LG then report `source`, and does the Cast entity go `off`/`idle`?).

- while watching several short YouTube videos back to back. Record which state it reports between videos (`paused`, `idle`, or something else) and how long that gap lasts.
- while using an HDMI source (done 2026-10-04 for PC: `on`, `source: PC`).

Use the results to:

- confirm or adjust the app detection order (casting already confirms the fallback to the extra entity's `app_name`)
- fill the built-in name table with the real values, including the launcher values to ignore
- confirm that the Cast entity reports `playing` for native apps. Any app that doesn't goes into the per-source list (or the Slaapkamer TV gets `app_open` as its default if most apps don't), and the README should say so.
- confirm the 60 s grace period default against the measured gaps between videos
- confirm whether HDMI sources report `playing`. If they don't, they go into the LG's per-source list, and the README should say so.

## Out of scope

- Daily/weekly/monthly sensors (possible spin-offs later, on top of `total_increasing` statistics)
- Combined activity sensor
- Overlap-aware combined totals
- Crediting time while HA was down
- Merging totals after a name mapping change
- Learning the counting mode per source automatically
