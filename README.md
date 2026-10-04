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
   - **Extra activity entity** (optional): a remote or media player that names the current app when the media player doesn't, or says `playing` when the media player can't. The TV counts as playing when either entity says `playing`, but the extra entity's `playing` only counts when it names the same app as the one on screen (or names no app), so a cast session left open on a phone for another app isn't counted; the media player alone decides whether the TV is on. See the example setups below.
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

`!ignore` means the value is never counted, which is useful for home screens and launchers, or for an input you never use. If an ignored source never counted any time, its sensors are removed when the integration reloads after you save the options. Matching is case-insensitive.

Changing a mapping after time has been counted starts a new sensor. The old sensor keeps its total and stops growing. Re-pick the source on the **Counting mode per source** screen if it used the other mode.

## Removing a TV or the integration

Deleting a tracked TV removes its device, sensors and per-TV totals. The combined totals keep the time it contributed.

Deleting the whole integration keeps its stored totals for now. If you add it again, the combined totals come back but the per-TV totals don't. A choice to restore or start fresh is planned.
