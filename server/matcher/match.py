from server.matcher.index import IndexedTrack, LibraryIndex, query_tokens
from server.matcher.normalize import normalize
from server.matcher.score import (
    AUTO_MARGIN,
    AUTO_MIN_DURATION,
    AUTO_MIN_VERSION,
    AUTO_SCORE,
    MAX_CANDIDATES,
    REPORT_THRESHOLD,
    STRONG_THRESHOLD,
    WEIGHT_ARTIST,
    WEIGHT_COMBINED,
    WEIGHT_DURATION,
    WEIGHT_TITLE,
    WEIGHT_VERSION,
    _ratio,
    _title_ratio,
    combine,
    duration_score,
    version_score,
)
from server.matcher.versions import TitleParts, extract_version
from server.models import MatchResult, PlaylistTrackInput, ScoredCandidate, VersionOut

_WEIGHTS = {
    "title": WEIGHT_TITLE,
    "artist": WEIGHT_ARTIST,
    "combined": WEIGHT_COMBINED,
    "version": WEIGHT_VERSION,
    "duration": WEIGHT_DURATION,
}


def _version_out(parts: TitleParts) -> VersionOut:
    return VersionOut(descriptors=list(parts.descriptors), remixer=parts.remixer)


def _score_candidate(
    query_parts: TitleParts,
    query_core: str,
    query_artist: str | None,
    query_all: str,
    query_duration: float | None,
    candidate: IndexedTrack,
) -> ScoredCandidate:
    facets: dict[str, float | None]
    if candidate.artist_norm is None:
        # Filename-only file: artist and title live in one undifferentiated
        # string, so compare against everything we know about the query.
        facets = {"combined": _ratio(query_all, candidate.all_norm)}
    else:
        facets = {
            "title": _title_ratio(query_core, candidate.core_norm),
            "artist": (
                _ratio(query_artist, candidate.artist_norm)
                if query_artist
                else None
            ),
        }
    facets["version"] = version_score(query_parts, candidate.parts)
    facets["duration"] = duration_score(
        query_duration, candidate.track.duration_sec
    )
    delta = None
    if query_duration is not None and candidate.track.duration_sec is not None:
        delta = round(candidate.track.duration_sec - query_duration, 1)
    return ScoredCandidate(
        track=candidate.track,
        score=round(combine(facets, _WEIGHTS), 4),
        parts=facets,
        version=_version_out(candidate.parts),
        duration_delta_sec=delta,
    )


def _bucket(scored: list[ScoredCandidate]) -> tuple[str, str | None]:
    if not scored:
        return "unmatched", None
    best = scored[0]
    if best.score >= AUTO_SCORE:
        margin_ok = (
            len(scored) == 1 or best.score - scored[1].score >= AUTO_MARGIN
        )
        version_part = best.parts.get("version") or 0.0
        duration_part = best.parts.get("duration")
        duration_ok = (
            duration_part >= AUTO_MIN_DURATION
            if duration_part is not None
            else version_part == 1.0
        )
        if margin_ok and version_part >= AUTO_MIN_VERSION and duration_ok:
            return "auto", best.track.id
    if any(candidate.score >= STRONG_THRESHOLD for candidate in scored):
        return "ambiguous", None
    return "unmatched", None


def match_one(track: PlaylistTrackInput, index: LibraryIndex) -> MatchResult:
    parts = extract_version(track.title)
    core_norm = normalize(parts.core_title)
    artist_bits = [track.artist] + list(parts.featured)
    artist_norm = normalize(" ".join(bit for bit in artist_bits if bit)) or None
    all_norm = " ".join(bit for bit in (artist_norm, core_norm) if bit)
    tokens = query_tokens(artist_norm, core_norm, parts)

    candidates = index.candidates(tokens, all_norm)
    scored = [
        _score_candidate(
            parts, core_norm, artist_norm, all_norm, track.duration_sec, candidate
        )
        for candidate in candidates
    ]
    scored = [c for c in scored if c.score >= REPORT_THRESHOLD]
    scored.sort(key=lambda c: c.score, reverse=True)
    scored = scored[:MAX_CANDIDATES]

    bucket, auto_id = _bucket(scored)
    return MatchResult(
        input=track,
        input_version=_version_out(parts),
        bucket=bucket,
        candidates=scored,
        auto_selected_id=auto_id,
    )


def match_playlist(
    tracks: list[PlaylistTrackInput], index: LibraryIndex
) -> list[MatchResult]:
    return [match_one(track, index) for track in tracks]
