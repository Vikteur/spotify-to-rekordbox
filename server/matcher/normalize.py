import re
import unicodedata

# Letters NFKD won't decompose to ASCII; both cases because this runs pre-lower.
_SPECIAL = str.maketrans(
    {
        "ø": "o", "Ø": "o", "æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe",
        "ß": "ss", "đ": "d", "Đ": "d", "ð": "d", "Ð": "d",
        "ł": "l", "Ł": "l", "þ": "th", "Þ": "th",
    }
)
_APOSTROPHES = re.compile(r"[’'`´]")
_PLUS_BETWEEN_WORDS = re.compile(r"(?<=\w)\+(?=\w)")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    """Fold text to lowercase ASCII words: 'Étienne & Co' → 'etienne and co'.

    NFKD folding also makes macOS NFD filenames equal to NFC tag values.
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.translate(_SPECIAL).lower()
    text = text.replace("&", " and ")
    text = _PLUS_BETWEEN_WORDS.sub(" and ", text)
    text = text.replace("$", "s")
    text = _APOSTROPHES.sub("", text)
    return _NON_ALNUM.sub(" ", text).strip()


def tokenize(text: str) -> list[str]:
    normalized = normalize(text)
    return normalized.split() if normalized else []
