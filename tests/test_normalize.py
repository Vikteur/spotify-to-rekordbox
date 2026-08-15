import pytest

from server.matcher.normalize import normalize, tokenize


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Étienne de Crécy", "etienne de crecy"),
        ("Møme & RØMANS", "mome and romans"),
        ("KE$HA", "kesha"),
        ("Don't Stop Believin'", "dont stop believin"),
        ("Kungs & Cookin’ On 3 Burners", "kungs and cookin on 3 burners"),
        ("A+B", "a and b"),
        ("Señorita (ft. Camila)", "senorita ft camila"),
        ("  spaced   out  ", "spaced out"),
        ("Cœur de pirate", "coeur de pirate"),
        ("Blitzkrieg ß", "blitzkrieg ss"),
        ("", ""),
    ],
)
def test_normalize(text: str, expected: str) -> None:
    assert normalize(text) == expected


def test_tokenize() -> None:
    assert tokenize("The XX - Intro!") == ["the", "xx", "intro"]
    assert tokenize("") == []
    assert tokenize("...") == []


def test_nfd_and_nfc_fold_to_the_same_tokens() -> None:
    nfc = "Crécy"  # é as one codepoint (tags)
    nfd = "Crécy"  # e + combining acute (macOS filenames)
    assert normalize(nfc) == normalize(nfd) == "crecy"
