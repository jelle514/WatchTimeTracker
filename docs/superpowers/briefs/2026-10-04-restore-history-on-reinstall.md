# Brief: keep or restore watch history when the integration is deleted

**Status:** Not started. Parked on 2026-10-04 to finish v0.1.0 first.
**Origin:** Final review of v0.1.0 (Important finding: no `async_remove_entry`).

## Problem

Deleting the Watch Time Tracker integration leaves its stored totals in `.storage/watch_time_tracker`. When the integration is added again:

- the old **combined** totals and their `All TVs` sensors come back;
- the old **per-TV** totals are deleted on the first setup, because their sub-entry IDs no longer exist.

The result is inconsistent, and the user never got to choose.

Home Assistant offers no way to ask a question while an integration is being deleted. `async_remove_entry` runs after the user has already confirmed, and it can't show a dialog. The choice therefore has to happen at another moment.

## Direction (owner's preference): ask when the integration is added again

1. **Deleting never loses data.**
   - In `async_remove_entry`, rewrite the store so the history is marked as "previous".
   - Keep the combined totals as they are.
   - Re-key each TV's totals by its media player entity ID. The removed entry's `subentries` give the media player for each sub-entry ID.
2. **Setup asks.** If previous history exists, the main config flow shows an extra step before creating the entry. For example: "Previous watch history found (124.5 h over 9 apps)." with the choices **Restore** and **Start fresh**.
   - **Start fresh:** `Store.async_remove()`.
   - **Restore:** keep the combined totals, and keep the per-TV history waiting.
3. **TVs get their own history back.** When a tracked TV is added with a media player that has waiting history, it adopts those totals. It only does so if the new sub-entry has no totals yet. Adopted history is removed from the waiting list.
4. **Stale cleanup must not delete waiting history.** The current setup step drops stored totals for unknown sub-entry IDs. Keep that, but leave the media-player-keyed history alone.

## Things to decide or check when picking this up

- Storage layout: e.g. `{"devices": {...}, "combined": {...}, "previous_devices": {media_player: totals}}`. This is a `minor_version` bump with a migration that adds an empty `previous_devices`.
- Whether waiting history should ever expire, or be listed in diagnostics so it's visible.
- A TV re-added with a **different** media player can't be matched automatically. Accept that, or offer a manual "adopt history from…" choice in the TV's setup.
- README: describe the restore choice under "Removing", and replace the interim note.

## Tests to write

- Removing the entry moves per-TV totals under their media player, and combined totals stay.
- Re-adding with history shows the restore step, which only appears when history exists.
- "Start fresh" deletes the store, so the new entry starts at 0.
- "Restore" brings the combined sensors back with their old totals.
- Adding a TV with a known media player adopts its totals. A second TV with the same media player is already blocked by the flow, so it's not a concern.
- Setup doesn't delete waiting history.
- Storage migration from 1.1 to the new minor version.

## Interim behaviour in v0.1.0

v0.1.0 has no `async_remove_entry`, so behaviour is as described under "Problem". The README says so under "Removing a TV".
