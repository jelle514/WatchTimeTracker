# Real-TV check

Task 0 of the implementation plan. Output of the Developer Tools → Template snippet in the plan, trimmed to the TV entities. Task 9 applies these findings.

## Woonkamer TV (LG webOS + built-in Chromecast)

### Casting F1 TV from a phone (2026-10-04)

```
media_player.lg_webos_smart_tv          | playing     | device_class: tv, source_list: [Disney+, HDMI 4, NPO Start, Netflix, Nintendo Switch Game Console, PC, Plex, Sonos Beam, YouTube]
media_player.lg_webos_tv_oled55c34la_2  | playing     | app_id: B3E81094, app_name: F1TV Chromecast, media_content_type: video
media_player.lg_webos_tv_oled55c34la    | unavailable |
```

The LG reports `playing` with **no `source`**. The built-in Chromecast (`..._2`) names the app. Use `..._2` as the LG's extra activity entity. Possible built-in name: `f1tv chromecast` → `F1 TV`.

### PC on HDMI (2026-10-04)

```
media_player.lg_webos_smart_tv          | on          | device_class: tv, source: PC, source_list: [same]
media_player.lg_webos_tv_oled55c34la_2  | off         |
media_player.lg_webos_tv_oled55c34la    | unavailable |
```

HDMI input reports `on`, not `playing`, so it is never counted in `playing_only`. PC (and presumably Nintendo Switch Game Console and HDMI 4) go in the LG's "Sources that count whenever they're open" list. The README's HDMI advice stands.

### Home screen (2026-10-04)

```
media_player.lg_webos_smart_tv          | on          | device_class: tv, source_list: [same]   (no source)
media_player.lg_webos_tv_oled55c34la_2  | off         |
media_player.lg_webos_tv_oled55c34la    | unavailable |
```

No app can be identified, so the raw app is "Unknown app". With the LG's default `playing_only` it isn't counted (`on` ≠ `playing`) and the activity sensor shows `idle`, which is correct. Because this looks exactly like an unknown app, "Unknown app" now counts only while `playing`, so the home screen is never counted, even with an `app_open` default.

### Native app: Live TV (2026-10-04)

```
media_player.lg_webos_smart_tv          | playing     | device_class: tv, media_content_type: channel, source: Live TV, source_list: [Disney+, HDMI 4, Live TV, NPO Start, Netflix, Nintendo Switch Game Console, PC, Plex, Sonos Beam, YouTube]
media_player.lg_webos_tv_oled55c34la_2  | off         |
media_player.lg_webos_tv_oled55c34la    | unavailable |
```

A native app reports `playing` with `source` set, and the built-in Chromecast is `off`, so the LG's `source` wins and the detection order stands. "Live TV" only appears in `source_list` while it is in use. The integration creates a sensor whenever `source_list` changes, so this is handled.

### Still to record

- Several short YouTube videos back to back: the state between videos and how long the gap lasts.

## Slaapkamer TV (Chromecast with Google TV)

### Home screen (2026-10-04)

```
media_player.slaapkamer_tv_2  | on  | app_id: com.google.android.apps.tv.launcherx, app_name: com.google.android.apps.tv.launcherx, device_class: tv
remote.slaapkamer_tv          | on  | current_activity: com.google.android.apps.tv.launcherx
media_player.chromecast       | off |
```

The Google Cast entity (`media_player.chromecast`) is `off` while the TV is on, so it can't be the media player that decides on/off for this TV. The Android TV Remote media player (`media_player.slaapkamer_tv_2`) reports `on` and the app. The launcher value is already in the built-in table as ignored, so the home screen isn't counted. Still open: does `slaapkamer_tv_2` ever report `playing`, or does `chromecast` turn `playing` during native app playback? That decides which entity is the media player and whether this TV needs the `app_open` default.

Also re-confirmed the same moment: LG casting F1 TV via the built-in Chromecast → LG `playing` with no `source`, `..._2` `playing` with `app_name: F1TV Chromecast`.

### YouTube playing (2026-10-04)

```
media_player.slaapkamer_tv_2  | on      | app_id/app_name: com.google.android.youtube.tv, device_class: tv
media_player.chromecast       | playing | app_id: 2C6A6E3D, app_name: YouTube, media_content_type: video, media_title: <video title>
remote.slaapkamer_tv          | on      | current_activity: com.google.android.youtube.tv
```

The Android TV Remote player (`slaapkamer_tv_2`) never says `playing`; it only knows on/off and the app. The Cast entity says `playing` with a friendly app name, but is `off` when no cast session is active (home screen). Neither entity alone gives both on/off and playing.

### Netflix open, nothing playing (2026-10-04)

```
media_player.slaapkamer_tv_2  | on      | app_id/app_name: com.netflix.ninja, device_class: tv
media_player.chromecast       | playing | app_id: Netflix, app_name: Netflix, media_content_type: video
remote.slaapkamer_tv          | on      | current_activity: com.netflix.ninja
```

The Cast entity reports `playing` while Netflix is only open (browsing). For Netflix on this TV, Cast `playing` effectively means "app open", so browsing time will be counted. No entity reports anything better, so this is a device limit, not something the integration can fix.

### Netflix playing (2026-10-04)

Identical to "Netflix open, nothing playing": `slaapkamer_tv_2` `on` (`com.netflix.ninja`), `chromecast` `playing` (`app_name: Netflix`), remote `com.netflix.ninja`. Confirmed: browsing and watching Netflix can't be told apart on this TV.

### Plex (native app) playing (2026-10-04)

```
media_player.slaapkamer_tv_2  | on      | app_id/app_name: com.plexapp.android, device_class: tv
media_player.chromecast       | playing | app_id: AndroidNativeApp, app_name: Plex, media_content_type: movie
remote.slaapkamer_tv          | on      | current_activity: com.plexapp.android
```

Same pattern as YouTube: the package name maps to Plex via the built-in table, and the Cast entity supplies `playing`.

### Casting YouTube from a phone (2026-10-04)

```
media_player.slaapkamer_tv_2  | on      | app_id/app_name: com.google.android.youtube.tv, device_class: tv
media_player.chromecast       | playing | app_id: 2C6A6E3D, app_name: YouTube, media_content_type: video, media_title: <video title>
remote.slaapkamer_tv          | on      | current_activity: com.google.android.youtube.tv
```

Identical to native YouTube: casting opens the native app, so no cast-receiver package appears and the detection order stands. Unverified: casting an app that has no Google TV app (e.g. F1 TV) might show a receiver package on `slaapkamer_tv_2`.

### YouTube paused (2026-10-04)

```
media_player.slaapkamer_tv_2  | on     | app_id/app_name: com.google.android.youtube.tv
media_player.chromecast       | paused | app_id: 2C6A6E3D, app_name: YouTube, media_title: <video title>
remote.slaapkamer_tv          | on     | current_activity: com.google.android.youtube.tv
```

The Cast entity reports `paused`, so the player state is `on` (not playing): the grace period applies and counting stops after it, as on the LG. YouTube is counted accurately on this TV; Netflix is not (see above).

### Casting F1 TV from a phone (2026-10-04)

```
media_player.slaapkamer_tv_2  | on      | app_id/app_name: com.google.android.apps.mediashell, device_class: tv
media_player.chromecast       | playing | app_id: B3E81094, app_name: F1TV Chromecast, media_content_type: video
remote.slaapkamer_tv          | on      | current_activity: com.google.android.apps.mediashell
```

An app without a Google TV app runs in the Cast receiver (`mediashell`). Only the Cast entity names the app. Fix: `mediashell` is ignored in the built-in table, and detection skips ignored candidates, so the app comes from the Cast entity's `app_name`.

### Disney+ open, nothing playing, right after casting F1 TV (2026-10-04)

```
media_player.slaapkamer_tv_2  | on        | app_id/app_name: com.disney.disneyplus, device_class: tv
media_player.chromecast       | buffering | app_id: B3E81094, app_name: F1TV Chromecast   (stale cast session)
remote.slaapkamer_tv          | on        | current_activity: com.disney.disneyplus
```

The Cast entity still shows the previous cast session. The app comes from the Android TV Remote player first (Disney+ via the built-in table), so the stale name isn't used, and `buffering` isn't `playing`, so nothing is counted, which is correct. Risk: a stale session that still says `playing` would make a newly opened app count while browsing.

### Disney+ playing (2026-10-04)

Identical to "Disney+ open": `slaapkamer_tv_2` `on` (`com.disney.disneyplus`), `chromecast` still the stale F1 TV session as `buffering`. Disney+ didn't report playback through the Cast entity here, so it would never count as playing. **Superseded below:** the stale F1 TV cast session blocked it. Re-test Disney+ after a fresh start (TV on, open Disney+ directly, no casting before). If the Cast entity then shows Disney+ `playing`/`paused`, no per-source entry is needed; otherwise tick Disney+ under "Sources that count whenever they're open".

## Summary: Slaapkamer TV setup

- Media player: `media_player.slaapkamer_tv_2` (Android TV Remote). Extra activity entity: `media_player.chromecast` (Google Cast).
- Default counting mode: only while playing. Per-source list: empty.
- YouTube and Plex are counted only while playing (the Cast entity reports `playing`/`paused`). Netflix counts whenever open (its Cast session says `playing` while browsing). Disney+ is counted only while playing (confirmed once the stale cast session was gone). The home screen is never counted.

### TV off (2026-10-04)

```
media_player.slaapkamer_tv_2  | off |
media_player.chromecast       | off |   (stale F1 TV session cleared)
remote.slaapkamer_tv          | off | current_activity: com.disney.disneyplus   (stale)
```

The main player being `off` wins: nothing is counted and the activity sensor shows `off`. The remote's stale `current_activity` is harmless.

### Disney+ open after TV off/on (2026-10-04)

```
media_player.slaapkamer_tv_2  | on     | app_id/app_name: com.disney.disneyplus
media_player.chromecast       | paused | app_id: B3E81094, app_name: F1TV Chromecast   (stale, survived TV off)
remote.slaapkamer_tv          | on     | current_activity: com.disney.disneyplus
```

The stale F1 TV cast session came back after the TV was off. The Cast entity can report a session for a different app than the one on screen, so its `playing` should only be trusted when its app matches the detected app.

Cause (confirmed): the phone still thought it was casting F1 TV, keeping the cast session alive in the background. After stopping it on the phone, the TV went back to the home screen: `slaapkamer_tv_2` `on` (launcher), `chromecast` `off`, remote launcher. A cast session left open on a phone is a realistic case, so the Cast entity's state can belong to another app than the one on screen.

### Disney+ playing, stale session gone (2026-10-04)

```
media_player.slaapkamer_tv_2  | on      | app_id/app_name: com.disney.disneyplus
media_player.chromecast       | playing | app_id: AndroidNativeApp, app_name: Disney+, media_content_type: video, media_title: Futurama
remote.slaapkamer_tv          | on      | current_activity: com.disney.disneyplus
```

Disney+ does report through the Cast entity. Both sides resolve to source key `disney`, so the same-app rule trusts it: Disney+ counts only while playing, like YouTube and Plex. The earlier "Disney+ doesn't report" finding was caused by the stale F1 TV session. No per-source entry needed.

### Still to record

- Optional: LG, several short YouTube videos back to back (owner: 60 s default is fine).
