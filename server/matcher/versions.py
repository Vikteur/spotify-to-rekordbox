"""Split a track title into its core name and version descriptors.

'Substitution (Purple Disco Machine Remix)' → core 'Substitution',
descriptors ('remix',), remixer 'purple disco machine'. The version facet is
scored separately from the title so an original and its remixes compare
honestly — the whole multiple-match picker rests on this split.
"""

import re
from dataclasses import dataclass, field

from server.matcher.normalize import tokenize

_BRACKET_RE = re.compile(r"\(([^()]*)\)|\[([^\[\]]*)\]|\{([^{}]*)\}")
_INLINE_FEAT_RE = re.compile(r"\s+(?:feat|ft|featuring)\.?\s+(.+)$", re.IGNORECASE)
_FEAT_LEADERS = {"feat", "ft", "featuring", "with"}

# Ordered: longer phrases first so 'radio edit' canonicalizes to 'radio', not
# 'radio' + 'edit'. Canonical None = the phrase means "no version" (erased).
_PHRASES: list[tuple[tuple[str, ...], str | None]] = [
    (("original", "mix"), None),
    (("original", "version"), None),
    (("original",), None),
    (("extended", "mix"), "extended"),
    (("extended", "version"), "extended"),
    (("extended", "edit"), "extended"),
    (("extended",), "extended"),
    (("radio", "edit"), "radio"),
    (("radio", "mix"), "radio"),
    (("radio", "version"), "radio"),
    (("radio",), "radio"),
    (("club", "mix"), "club"),
    (("club", "edit"), "club"),
    (("dub", "mix"), "dub"),
    (("sped", "up"), "spedup"),
    (("slowed", "and", "reverb"), "slowed"),
    (("slowed", "reverb"), "slowed"),
    (("slowed",), "slowed"),
    (("a", "cappella"), "acapella"),
    (("acapella",), "acapella"),
    (("remastered",), "remaster"),
    (("remaster",), "remaster"),
    (("remix",), "remix"),
    (("rmx",), "remix"),
    (("edit",), "edit"),
    (("mix",), "mix"),
    (("dub",), "dub"),
    (("vip",), "vip"),
    (("bootleg",), "bootleg"),
    (("mashup",), "mashup"),
    (("rework",), "rework"),
    (("refix",), "refix"),
    (("flip",), "flip"),
    (("live",), "live"),
    (("acoustic",), "acoustic"),
    (("instrumental",), "instrumental"),
    (("cover",), "cover"),
    (("version",), "version"),
]

# A segment with a keyword still isn't a descriptor if it carries a lot of
# other text — "(I Can't Get No)" style fragments must stay in the title.
_MAX_EXTRA_TOKENS = 4


@dataclass(frozen=True)
class TitleParts:
    core_title: str
    descriptors: tuple[str, ...]
    remixer: str | None
    featured: tuple[str, ...] = field(default=())


def _classify_segment(text: str) -> tuple[list[str], list[str]] | None:
    """→ (canonical descriptors, leftover tokens) or None if not a descriptor."""
    tokens = tokenize(text)
    if not tokens:
        return None
    canonicals: list[str] = []
    leftover: list[str] = []
    matched_any = False
    i = 0
    while i < len(tokens):
        for phrase, canonical in _PHRASES:
            if tuple(tokens[i : i + len(phrase)]) == phrase:
                matched_any = True
                if canonical is not None:
                    canonicals.append(canonical)
                i += len(phrase)
                break
        else:
            leftover.append(tokens[i])
            i += 1
    leftover = [token for token in leftover if not token.isdigit()]
    if not matched_any or len(leftover) > _MAX_EXTRA_TOKENS:
        return None
    return canonicals, leftover


def extract_version(title: str) -> TitleParts:
    descriptors: list[str] = []
    remixer_tokens: list[str] = []
    featured: list[str] = []

    def consume_segment(text: str) -> bool:
        tokens = tokenize(text)
        if tokens and tokens[0] in _FEAT_LEADERS:
            rest = " ".join(tokens[1:])
            if rest:
                featured.append(rest)
            return True
        classified = _classify_segment(text)
        if classified is None:
            return False
        canonicals, leftover = classified
        descriptors.extend(canonicals)
        remixer_tokens.extend(leftover)
        return True

    def bracket_repl(match: re.Match) -> str:
        segment = next(group for group in match.groups() if group is not None)
        return "" if consume_segment(segment) else match.group(0)

    core = _BRACKET_RE.sub(bracket_repl, title)

    # Trailing ' - Radio Edit' style suffixes (repeat: ' - Edit - Live' etc.).
    changed = True
    while changed:
        changed = False
        head, separator, tail = core.rpartition(" - ")
        if separator and head.strip() and consume_segment(tail):
            core = head
            changed = True

    inline = _INLINE_FEAT_RE.search(core)
    if inline:
        featured.append(" ".join(tokenize(inline.group(1))))
        core = core[: inline.start()]

    core = re.sub(r"\s{2,}", " ", core).strip(" -–—\t ")
    if not core.strip():
        core = title.strip()

    unique_descriptors = tuple(sorted(set(descriptors)))
    remixer = " ".join(remixer_tokens) or None
    return TitleParts(
        core_title=core,
        descriptors=unique_descriptors,
        remixer=remixer,
        featured=tuple(name for name in featured if name),
    )
