import pytest

from server.matcher.versions import extract_version


@pytest.mark.parametrize(
    ("title", "core", "descriptors", "remixer"),
    [
        ("Am I Wrong", "Am I Wrong", (), None),
        ("Am I Wrong (Original Mix)", "Am I Wrong", (), None),
        ("Substitution (Purple Disco Machine Remix)", "Substitution", ("remix",), "purple disco machine"),
        ("Am I Wrong [Superdiscount Extended Edit]", "Am I Wrong", ("extended",), "superdiscount"),
        ("Animals - Radio Edit", "Animals", ("radio",), None),
        ("Animals (Radio Edit)", "Animals", ("radio",), None),
        ("Levels (Remastered 2011)", "Levels", ("remaster",), None),
        ("Divide - Part 2", "Divide - Part 2", (), None),
        ("(I Can't Get No) Satisfaction", "(I Can't Get No) Satisfaction", (), None),
        ("One (Club Mix)", "One", ("club",), None),
        ("Song (VIP)", "Song", ("vip",), None),
        ("Song (Acoustic)", "Song", ("acoustic",), None),
        ("Song (Sped Up)", "Song", ("spedup",), None),
        ("Faded (Restrung)", "Faded (Restrung)", (), None),
        ("Greyhound - Extended Mix", "Greyhound", ("extended",), None),
        ("Titel - Live - Radio Edit", "Titel", ("live", "radio"), None),
    ],
)
def test_extract_version(
    title: str, core: str, descriptors: tuple[str, ...], remixer: str | None
) -> None:
    parts = extract_version(title)
    assert parts.core_title == core
    assert parts.descriptors == descriptors
    assert parts.remixer == remixer


@pytest.mark.parametrize(
    ("title", "core", "featured"),
    [
        ("Peaches (feat. Daniel Caesar & Giveon)", "Peaches", ("daniel caesar and giveon",)),
        ("One More Time (feat. Someone) [Club Mix]", "One More Time", ("someone",)),
        ("Song (with Dua Lipa)", "Song", ("dua lipa",)),
        ("I'm the One feat. DJ Khaled", "I'm the One", ("dj khaled",)),
        ("Solo ft Demi Lovato", "Solo", ("demi lovato",)),
    ],
)
def test_featured_extraction(title: str, core: str, featured: tuple[str, ...]) -> None:
    parts = extract_version(title)
    assert parts.core_title == core
    assert parts.featured == featured


def test_all_descriptor_title_keeps_original() -> None:
    parts = extract_version("Extended Mix")
    assert parts.core_title == "Extended Mix"


def test_spotify_remix_title_is_versioned_too() -> None:
    parts = extract_version("Sweet Disposition (John Summit Remix)")
    assert parts.descriptors == ("remix",)
    assert parts.remixer == "john summit"
