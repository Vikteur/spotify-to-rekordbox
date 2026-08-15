import re

_NUMBER_PREFIX = re.compile(r"^\s*\d{1,3}\s*[.)\-]?\s+")
_SEPARATORS = (" - ", " – ", " — ")


def parse_filename(stem: str) -> tuple[str | None, str]:
    """Best-effort '01. Artist - Title' → (artist, title) for untagged files.

    Returns (None, cleaned_stem) when no artist/title separator is present.
    """
    cleaned = stem.replace("_", " ").strip()
    cleaned = _NUMBER_PREFIX.sub("", cleaned)
    for separator in _SEPARATORS:
        if separator in cleaned:
            artist, title = cleaned.split(separator, 1)
            return artist.strip() or None, title.strip() or cleaned
    return None, cleaned
