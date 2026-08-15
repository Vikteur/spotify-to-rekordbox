"""Facet scoring and bucket constants — the single calibration point.

A pair is scored on four facets (title, artist, version, duration) and
combined with fixed weights, renormalized when a facet is unavailable.
Buckets: auto needs a high, well-separated, version-compatible best
candidate; anything with a plausible candidate becomes ambiguous (the user
picks); the rest is unmatched.
"""

from rapidfuzz import fuzz

from server.matcher.versions import TitleParts

REPORT_THRESHOLD = 0.45   # below this a candidate isn't shown at all
STRONG_THRESHOLD = 0.60   # "could plausibly be it" → ambiguous bucket
AUTO_SCORE = 0.82
AUTO_MARGIN = 0.10        # best - second best
AUTO_MIN_VERSION = 0.90   # never auto-pick a different version
AUTO_MIN_DURATION = 0.55  # ~ within 22 s
MAX_CANDIDATES = 8

WEIGHT_TITLE = 0.40
WEIGHT_ARTIST = 0.30
WEIGHT_COMBINED = 0.70    # replaces title+artist for filename-only candidates
WEIGHT_VERSION = 0.15
WEIGHT_DURATION = 0.15

# Version classes: how bad is offering this when the query asked "original"?
_LIGHT = {"extended", "radio", "edit", "club", "mix", "version"}          # 0.60
_REMIXER_SAME_MIN = 0.85
_REMIXER_ONE_SIDED = 0.85  # "(Remix)" vs "(X Remix)" — probably the same
_REMASTER_FACTOR = 0.90


def _ratio(a: str, b: str) -> float:
    """Set semantics: extra tokens on one side don't hurt. Right for artists
    (query 'A, B, C' vs a tag with just 'A') and filename blobs."""
    if not a or not b:
        return 0.0
    return fuzz.token_set_ratio(a, b) / 100


def _title_ratio(a: str, b: str) -> float:
    """Order-insensitive but length-sensitive: 'Anthem' must NOT score 1.0
    against 'Other Anthem Of Ours' the way token_set_ratio would."""
    if not a or not b:
        return 0.0
    return fuzz.token_sort_ratio(a, b) / 100


def _remixer_same(a: str, b: str) -> bool:
    # Character-level and strict: 'Artist Two' vs 'Artist Three' share a token
    # but are different remixers.
    return fuzz.ratio(a, b) / 100 >= _REMIXER_SAME_MIN


def version_score(query: TitleParts, candidate: TitleParts) -> float:
    query_set = set(query.descriptors) - {"remaster"}
    cand_set = set(candidate.descriptors) - {"remaster"}
    remaster_differs = ("remaster" in query.descriptors) != (
        "remaster" in candidate.descriptors
    )
    factor = _REMASTER_FACTOR if remaster_differs else 1.0

    if query_set == cand_set:
        if query.remixer and candidate.remixer:
            base = 1.0 if _remixer_same(query.remixer, candidate.remixer) else 0.20
        elif query.remixer or candidate.remixer:
            base = _REMIXER_ONE_SIDED if query_set else 1.0
        else:
            base = 1.0
        return base * factor

    if not query_set or not cand_set:
        other = query_set or cand_set
        base = 0.60 if other <= _LIGHT else 0.25
    elif query_set & cand_set:
        base = 0.40
    else:
        base = 0.20
    return base * factor


def duration_score(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    delta = abs(a - b)
    return 1.0 if delta <= 3 else max(0.0, 1 - (delta - 3) / 42)


def combine(parts: dict[str, float | None], weights: dict[str, float]) -> float:
    """Weighted mean over the facets that are actually available."""
    total = 0.0
    weight_sum = 0.0
    for name, value in parts.items():
        if value is None:
            continue
        weight = weights[name]
        total += weight * value
        weight_sum += weight
    return total / weight_sum if weight_sum else 0.0
