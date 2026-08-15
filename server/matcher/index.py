from dataclasses import dataclass

from rapidfuzz import fuzz, process

from server.matcher.normalize import normalize, tokenize
from server.matcher.versions import TitleParts, extract_version
from server.models import LibraryTrack

RARE_DF = 50          # a token this uncommon makes a single hit interesting
MIN_TOKEN_HITS = 2
CANDIDATE_CAP = 300
FALLBACK_LIMIT = 50   # library-wide fuzzy scan when the index finds nothing
FALLBACK_CUTOFF = 50  # rapidfuzz 0-100


@dataclass
class IndexedTrack:
    track: LibraryTrack
    parts: TitleParts
    core_norm: str
    artist_norm: str | None
    all_norm: str          # artist + core title (+featured/remixer) in one string
    tokens: set[str]


def _build(track: LibraryTrack) -> IndexedTrack:
    parts = extract_version(track.title)
    core_norm = normalize(parts.core_title)
    artist_bits = [track.artist or ""] + list(parts.featured)
    artist_norm = normalize(" ".join(bit for bit in artist_bits if bit)) or None
    all_bits = [artist_norm or "", core_norm, parts.remixer or ""]
    all_norm = " ".join(bit for bit in all_bits if bit).strip()
    tokens = set(all_norm.split())
    return IndexedTrack(
        track=track,
        parts=parts,
        core_norm=core_norm,
        artist_norm=artist_norm,
        all_norm=all_norm,
        tokens=tokens,
    )


class LibraryIndex:
    def __init__(self, tracks: list[LibraryTrack]) -> None:
        self.items = [_build(track) for track in tracks]
        self.postings: dict[str, list[int]] = {}
        for ordinal, item in enumerate(self.items):
            for token in item.tokens:
                self.postings.setdefault(token, []).append(ordinal)
        self._all_norms = [item.all_norm for item in self.items]

    def candidates(self, query_tokens: set[str], query_norm: str) -> list[IndexedTrack]:
        hits: dict[int, int] = {}
        rare_hit: set[int] = set()
        for token in query_tokens:
            postings = self.postings.get(token)
            if not postings:
                continue
            rare = len(postings) <= RARE_DF
            for ordinal in postings:
                hits[ordinal] = hits.get(ordinal, 0) + 1
                if rare:
                    rare_hit.add(ordinal)
        selected = [
            (count, ordinal)
            for ordinal, count in hits.items()
            if count >= MIN_TOKEN_HITS or ordinal in rare_hit
        ]
        selected.sort(reverse=True)
        if selected:
            return [self.items[ordinal] for _, ordinal in selected[:CANDIDATE_CAP]]
        return self._fallback(query_norm)

    def _fallback(self, query_norm: str) -> list[IndexedTrack]:
        """No token overlap at all (typo'd tags): fuzzy-scan the whole library."""
        if not query_norm or not self.items:
            return []
        found = process.extract(
            query_norm,
            self._all_norms,
            scorer=fuzz.token_set_ratio,
            limit=FALLBACK_LIMIT,
            score_cutoff=FALLBACK_CUTOFF,
        )
        return [self.items[ordinal] for _, _, ordinal in found]


def query_tokens(artist_norm: str | None, core_norm: str, parts: TitleParts) -> set[str]:
    tokens = set(core_norm.split())
    if artist_norm:
        tokens.update(artist_norm.split())
    if parts.remixer:
        tokens.update(parts.remixer.split())
    return tokens
