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

No app can be identified, so the raw app is "Unknown app". With the LG's default `playing_only` it isn't counted (`on` ≠ `playing`) and the activity sensor shows `idle`, which is correct. With an `app_open` default, home-screen time would be counted as "Unknown app".

### Still to record

- A native app playing (YouTube, Netflix): is `source` set, and is `..._2` `off`?
- Several short YouTube videos back to back: the state between videos and how long the gap lasts.

## Slaapkamer TV (Chromecast with Google TV)

### Still to record

- The home screen.
- YouTube, Netflix, Plex and Disney+, each while playing and while paused (`media_player.chromecast`, `remote.slaapkamer_tv`, `media_player.slaapkamer_tv_2`).
