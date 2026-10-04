# Backlog

Small follow-ups left after the v0.1.0 final review (2026-10-04). Each is minor; none blocks use.

- **Restore or start fresh after re-adding the integration.** See [2026-10-04-restore-history-on-reinstall.md](2026-10-04-restore-history-on-reinstall.md).
- **Renamed media player entity ID stops tracking silently.** TVs are tracked by `entity_id`. Renaming it leaves the Activity sensor on `off`. Options: log a warning once HA has started if the entity is missing, or store the entity registry ID and resolve it at setup.
- **Extra activity entity can be the media player itself.** It's harmless, but the "Add tracked TV" form could reject it with a form error.
- **"All TVs" device name is hard-coded English** (`sensor.py`). Use a device `translation_key` if more languages are added.
- **Measure the gap between back-to-back YouTube videos on the LG** and confirm the 60 s grace default (owner expects it's fine).
- **Optional tests:** an extra entity reporting `playing` with no app, Store migration, the delayed save firing, an options change reloading the entry.
