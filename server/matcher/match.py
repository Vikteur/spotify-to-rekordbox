from server.matcher.index import IndexedTrack, LibraryIndex, query_tokens
from server.matcher.normalize import normalize
from server.matcher.score import (
    AUTO_MARGIN,
    AUTO_MIN_DURATION,
    AUTO_MIN_VERSION,
    AUTO_SCORE,
    MAX_CANDIDATES,
    PLAYLIST_BONUS,
    PLAYLIST_BONUS_CAP,
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
from server.matcher.signature import signature_id
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
        # Too close to call on score alone is still decided when exactly one
        # of the contenders is a track you actually play. Order matters: the
        # single-candidate case must short-circuit before scored[1] is read.
        margin_ok = (
            len(scored) == 1
            or best.score - scored[1].score >= AUTO_MARGIN
            or (bool(best.playlists) and not scored[1].playlists)
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


def _ranked(candidate: ScoredCandidate) -> float:
    """Score with the playlist nudge applied — used for ordering only."""
    return candidate.score + PLAYLIST_BONUS * min(
        len(candidate.playlists), PLAYLIST_BONUS_CAP
    )


def match_one(
    track: PlaylistTrackInput,
    index: LibraryIndex,
    preferences: dict[str, str] | None = None,
    membership: dict[str, list[str]] | None = None,
) -> MatchResult:
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
    if membership:
        for candidate in scored:
            candidate.playlists = membership.get(candidate.track.id, [])
    scored.sort(key=_ranked, reverse=True)
    scored = scored[:MAX_CANDIDATES]

    bucket, auto_id = _bucket(scored)

    # A version you picked before wins over whatever scoring would have chosen.
    from_preference = False
    preferred_id = (preferences or {}).get(signature_id(track.artist, track.title))
    if preferred_id is not None:
        preferred = next((c for c in scored if c.track.id == preferred_id), None)
        if preferred is None and preferred_id in index.by_track_id:
            # Still honour the choice even if this playlist's wording scored it
            # too low to list; the song is the same one you decided about.
            preferred = _score_candidate(
                parts, core_norm, artist_norm, all_norm, track.duration_sec,
                index.by_track_id[preferred_id],
            )
            scored = [preferred, *scored][:MAX_CANDIDATES]
        if preferred is not None:
            scored = [preferred, *[c for c in scored if c.track.id != preferred_id]]
            auto_id = preferred_id
            from_preference = True

    return MatchResult(
        input=track,
        input_version=_version_out(parts),
        bucket=bucket,
        candidates=scored,
        auto_selected_id=auto_id,
        from_preference=from_preference,
    )


def match_playlist(
    tracks: list[PlaylistTrackInput],
    index: LibraryIndex,
    preferences: dict[str, str] | None = None,
    membership: dict[str, list[str]] | None = None,
) -> list[MatchResult]:
    return [match_one(track, index, preferences, membership) for track in tracks]
