# Spotify → rekordbox

A small local webapp that turns a **public Spotify playlist** into a **rekordbox playlist built from music files you already own**:

1. Point it at your music folder — it scans every audio file (tags + filenames)
2. Paste a Spotify playlist link (no Spotify account or API key needed)
3. It fuzzy-matches each Spotify track against your files; when several versions exist (original + remixes), **you pick one from a dropdown**
4. Download a `.m3u8` or rekordbox `.xml` playlist and import it into rekordbox

Everything runs on your machine. Nothing is uploaded anywhere.

![Screenshot](docs/screenshot.png)

## Prerequisites

- Python ≥ 3.11
- Node ≥ 20
- rekordbox (5/6/7) to import the result
- A **public** Spotify playlist URL (or any tracklist as text)

## Setup

```bash
# Python backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Frontend
npm install
```

## Run

```bash
npm run dev        # dev mode → open http://localhost:5173
```

or, closer to "production":

```bash
npm run build
npm start          # → open http://127.0.0.1:8000
```

Both need the venv active (the server runs via `python -m uvicorn`). The server binds to `127.0.0.1` only — it can read your local folders, so never expose it on a network.

## Usage notes

- **Scanning**: the first scan of a big folder takes a while (every file's tags are read); results are cached by file path + size + mtime, so the next scan takes seconds. Retagged files are re-read automatically; use **Force rescan** to ignore the cache entirely.
- **Files without tags** are matched by filename (`Artist - Title.mp3` patterns).
- **iTunes / Apple Music**: iTunes songs are `.m4a` files and fully supported (AAC and Apple Lossless). Typical folders: macOS `~/Music/Music/Media.localized/` (older: `~/Music/iTunes/iTunes Media/Music/`), Windows `C:\Users\<you>\Music\iTunes\iTunes Media\Music\`. **`.m4p` files** (pre-2010 iTunes purchases and Apple Music *subscription* downloads) are DRM-locked — rekordbox can't play them, so the scanner counts and reports them instead of matching them.
- **Playlists over ~100 tracks**: Spotify's public embed data stops around 100 tracks. The app warns you when this happens — paste the full tracklist as text instead (in Spotify select all tracks, or use any text list with one `Artist - Title` per line).
- **Matching**: green *auto* rows are confident matches (still overridable); amber *pick one* rows have several plausible files — that's the remix picker; *no match* rows list weak guesses if any. The dropdown shows each candidate's version (`[x remix]`, `[extended]`…), duration difference vs Spotify, format/bitrate, and score.

## Importing into rekordbox

**M3U8 (recommended):** rekordbox → `File › Import › Import Playlist` → pick the downloaded `.m3u8`. Tracks already in your collection are matched by file path (cues/grids untouched); new files are added and analyzed.

**rekordbox XML:** `Preferences › Advanced › Database › rekordbox xml` → browse to the downloaded `.rekordbox.xml`. Show the xml pane via `Preferences › View › Layout › rekordbox xml`. In the tree's *rekordbox xml* section, right-click the playlist → `Import Playlist`.

## Checking the Spotify fetch

The playlist fetch uses Spotify's public embed page (the same trick "no sign-in" converter sites use) because Spotify's official API stopped allowing anonymous metadata access in 2026. Verify it works from your machine:

```bash
python scripts/probe_spotify.py "https://open.spotify.com/playlist/<id>"
```

`OK` + a track list means you're good. If Spotify changes their page format some day, the app tells you and the paste-text fallback always keeps working (plan B for developers: swap `server/spotify/` for the `spotifyscraper` PyPI package behind the same interface).

## Limitations (POC)

- Public playlists only (no Spotify login) — make a private playlist public for a minute, or paste it as text
- Embed data caps at ~100 tracks (warned in-app; text paste has no cap)
- Matching is metadata-only (tags/filenames/duration) — no audio fingerprinting
- One library folder at a time

## Troubleshooting

- **Folder not found**: quotes and trailing slashes are trimmed automatically; check the path and permissions. `~` works.
- **Wrong matches after retagging**: hit **Force rescan**.
- **Accents look wrong after M3U8 import on Windows**: tell me — adding a UTF-8 BOM to the export is a one-line change.
- **Reset everything**: delete the `.cache/` folder.

## Development

```bash
.venv/bin/pytest           # 99 tests: parser fixtures, scanner, matcher calibration, exports, API
npm run typecheck          # strict TS on the client
node scripts/screenshot.mjs <music-folder>   # regenerate docs/screenshot.png (app must be running)
```

The matching thresholds live in `server/matcher/score.py`; `tests/test_matcher.py` is the calibration harness — tune, run, repeat.

> This folder is fully self-contained (own dependencies, no imports from the surrounding repo) so it can be copied out into its own repository as-is.
