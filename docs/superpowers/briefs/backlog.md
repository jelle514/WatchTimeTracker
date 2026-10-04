# Backlog

Small follow-ups left after the v0.1.0 final review (2026-10-04). Each is minor; none blocks use.

- **Restore or start fresh after re-adding the integration.** See [2026-10-04-restore-history-on-reinstall.md](2026-10-04-restore-history-on-reinstall.md).
- **Ignoring a source after it appeared leaves its sensors.** Found 2026-10-04 with `Sonos Beam = !ignore` (an HDMI ARC input on the LG that's never selected). Its stored 0-minute totals make `sensor.py` recreate the Woonkamer and All TVs sensors at every startup, even after deleting them in HA. Fix: at setup, drop stored sources with 0 minutes whose stored display name now resolves to ignored (`resolve(display_name, overrides) is None`), for both device and combined totals, and remove their entities from the entity registry. Never drop a source with recorded time. Test with the Sonos Beam case.
- **Renamed media player entity ID stops tracking silently.** TVs are tracked by `entity_id`. Renaming it leaves the Activity sensor on `off`. Options: log a warning once HA has started if the entity is missing, or store the entity registry ID and resolve it at setup.
- **Extra activity entity can be the media player itself.** It's harmless, but the "Add tracked TV" form could reject it with a form error.
- **"All TVs" device name is hard-coded English** (`sensor.py`). Use a device `translation_key` if more languages are added.
- **Measure the gap between back-to-back YouTube videos on the LG** and confirm the 60 s grace default (owner expects it's fine).
- **Optional tests:** an extra entity reporting `playing` with no app, Store migration, the delayed save firing, an options change reloading the entry.
