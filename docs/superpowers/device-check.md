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

### Still to record

- YouTube paused: does `media_player.chromecast` switch to `paused`?
- Plex and Disney+, each while playing and while paused (`media_player.chromecast`, `remote.slaapkamer_tv`, `media_player.slaapkamer_tv_2`).
