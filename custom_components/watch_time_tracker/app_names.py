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
