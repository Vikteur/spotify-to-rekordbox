import json
from pathlib import Path

import pytest

from server.spotify.parse_embed import (
    BadPlaylistUrl,
    EmbedParseError,
    parse_embed_html,
    parse_playlist_url,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _page_with(next_data: dict) -> str:
    return (
        "<html><body><script id=\"__NEXT_DATA__\" type=\"application/json\">"
        + json.dumps(next_data)
        + "</script></body></html>"
    )


def test_parse_happy_fixture() -> None:
    result = parse_embed_html((FIXTURES / "embed_playlist.html").read_text("utf-8"))
    assert result["name"] == "Test Warmup"
    assert result["owner_name"] == "viktor"
    assert result["total"] is None
    assert result["truncated"] is False
    tracks = result["tracks"]
    assert len(tracks) == 3
    assert tracks[0] == {
        "index": 0,
        "artist": "Étienne de Crécy",
        "title": "Am I Wrong",
        "duration_sec": 213,
    }
    assert tracks[1]["duration_sec"] == 371  # durationMs variant
    assert tracks[1]["artist"] == "Purple Disco Machine, Kungs"
    assert tracks[2]["duration_sec"] is None


def test_parse_truncated_fixture() -> None:
    result = parse_embed_html((FIXTURES / "embed_truncated.html").read_text("utf-8"))
    assert result["total"] == 342
    assert result["truncated"] is True
    assert len(result["tracks"]) == 5


def test_hundred_tracks_without_total_is_flagged_truncated() -> None:
    items = [
        {"title": f"Song {i}", "subtitle": "A", "duration": 180000} for i in range(100)
    ]
    entity = {"name": "Long", "trackList": items}
    result = parse_embed_html(
        _page_with({"props": {"pageProps": {"state": {"data": {"entity": entity}}}}})
    )
    assert result["truncated"] is True

    entity_99 = {"name": "Short enough", "trackList": items[:99]}
    result_99 = parse_embed_html(
        _page_with({"props": {"pageProps": {"state": {"data": {"entity": entity_99}}}}})
    )
    assert result_99["truncated"] is False


def test_entity_moved_deeper_is_still_found() -> None:
    entity = {
        "name": "Hidden",
        "trackList": [{"title": "X", "subtitle": "Y", "duration": 60000}],
    }
    page = _page_with(
        {"props": {"pageProps": {"weird": [{"nested": {"entity": entity}}]}}}
    )
    result = parse_embed_html(page)
    assert result["name"] == "Hidden"
    assert result["tracks"][0]["title"] == "X"


def test_tracklist_as_items_dict_with_total() -> None:
    entity = {
        "name": "Dict shape",
        "trackList": {
            "items": [{"title": "X", "subtitle": "Y", "durationMs": 61000}],
            "totalCount": 7,
        },
    }
    result = parse_embed_html(
        _page_with({"props": {"pageProps": {"state": {"data": {"entity": entity}}}}})
    )
    assert result["total"] == 7
    assert result["truncated"] is True
    assert result["tracks"][0]["duration_sec"] == 61


def test_artists_array_fallback() -> None:
    entity = {
        "name": "Artist array",
        "trackList": [
            {
                "title": "X",
                "artists": [{"name": "First"}, {"name": "Second"}],
                "duration": 90000,
            }
        ],
    }
    result = parse_embed_html(
        _page_with({"props": {"pageProps": {"state": {"data": {"entity": entity}}}}})
    )
    assert result["tracks"][0]["artist"] == "First, Second"


def test_missing_next_data_raises() -> None:
    with pytest.raises(EmbedParseError, match="__NEXT_DATA__"):
        parse_embed_html("<html><body>login wall</body></html>")


def test_no_entity_raises() -> None:
    with pytest.raises(EmbedParseError, match="entity"):
        parse_embed_html(_page_with({"props": {"pageProps": {}}}))


@pytest.mark.parametrize(
    "text",
    [
        "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc123",
        "https://open.spotify.com/intl-nl/playlist/37i9dQZF1DXcBWIGoYBM5M",
        "open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
        "37i9dQZF1DXcBWIGoYBM5M",
        '  "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"  ',
    ],
)
def test_parse_playlist_url_accepts(text: str) -> None:
    assert parse_playlist_url(text) == "37i9dQZF1DXcBWIGoYBM5M"


@pytest.mark.parametrize(
    "text",
    [
        "https://open.spotify.com/album/4aawyAB9vmqN3uQ7FjRGTy",
        "https://open.spotify.com/track/11dFghVXANMlKmJXsNCbNl",
        "https://example.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
        "not a url at all",
    ],
)
def test_parse_playlist_url_rejects(text: str) -> None:
    with pytest.raises(BadPlaylistUrl):
        parse_playlist_url(text)
