"""A stable identity for "the same song in a Spotify playlist".

Used to remember which of your files you picked for a track, so the choice
survives into future playlists. Built from the normalized artist, the core
title and the version descriptors — so "Strobe" and "Strobe (Radio Edit)"
are deliberately *different* songs with independent choices, while
"Peaches (feat. Daniel Caesar)" and "Peaches" are the same one.

Featured artists are excluded on purpose: playlists list them
inconsistently, and a preference that only applies half the time is worse
than useless.
"""

import hashlib

from server.matcher.normalize import normalize
from server.matcher.versions import extract_version


def signature_of(artist: str, title: str) -> str:
    parts = extract_version(title)
    return "|".join(
        (
            normalize(artist or ""),
            normalize(parts.core_title),
            "+".join(sorted(parts.descriptors)),
            normalize(parts.remixer or ""),
        )
    )


def signature_id(artist: str, title: str) -> str:
    """URL-safe handle for a signature (preferences are addressed by this)."""
    return hashlib.sha1(signature_of(artist, title).encode("utf-8")).hexdigest()[:16]
