# Spotify → rekordbox — the backend

The API behind Rekord Match: it scans your music, matches Spotify playlists
against it, keeps the couples intake, and builds the files you import into
rekordbox. No UI lives here.

Given a **public Spotify playlist** it produces a **rekordbox playlist built
from music files you already own**:

1. A named library (one per device) is loaded from a **scanned music folder**,
   an **imported rekordbox XML export**, or both
2. A Spotify playlist link is fetched (no Spotify account or API key needed)
3. Each track is fuzzy-matched against the library; when several versions exist
   (original + remixes) the DJ picks one, and the pick is **remembered** as
   that song's default for every future playlist
4. It exports a `.m3u8` or rekordbox `.xml` playlist, plus a `.txt` shopping
   list of everything the playlist wanted but the library doesn't have

The library is kept in a local SQLite file, so you scan once — not on every
launch.

## The three repos

| Repo | What it holds |
| --- | --- |
| `spotify-to-rekordbox` (this one) | The backend: FastAPI, the matcher, the SQLite library, and the deployment topology for all three |
| [`rekord-dj`](https://github.com/Vikteur/rekord-dj) | The DJ app — library, matching, exports, and the couples panel |
| [`rekord-couple`](https://github.com/Vikteur/rekord-couple) | The couple/friends intake SPA at `/g/<token>` |

The front-ends call `/api` on their own origin; the proxy routes that here, so
there is no CORS anywhere in the stack. Nothing in this repo serves HTML.

## Prerequisites

- Python ≥ 3.11
- rekordbox (5/6/7) to import the result
- A **public** Spotify playlist URL (or any tracklist as text)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python -m server.run             # http://127.0.0.1:8000
python -m server.run --reload    # reload on edit
```

Then start whichever front-end you're working on, in its own checkout; its dev
server proxies `/api` back here. `PORT=8010 python -m server.run` moves the API,
and the front-ends follow with `API_URL=http://127.0.0.1:8010 npm run dev`.

The server binds to `127.0.0.1` only — it can read your local folders, so never
expose it on a network without a proxy in front.

**There is no login.** No account, no sign-in, no Spotify authentication. The
only credential in the system is a magic-link token, and that is what a *guest*
gets, not something the DJ needs.

> ⚠️ **Auth is switched off on this branch, on purpose and temporarily.** The
> magic-link checks are bypassed (`AUTH_DISABLED`, `server/couples_api.py`) and
> the proxy password is commented out in `deploy/Caddyfile` and
> `deploy/nginx/rekord.conf`. Deployed as-is, the DJ side is public — including
> `/api/couples`, which hands every couple's magic link to any caller, and
> `/api/scan`, which reads folders on the server. To put it back: set
> `AUTH_DISABLED=0` and un-comment the two `basic_auth` blocks.

## Your libraries

Music is organised into **named libraries** — normally one per device
("MacBook", "Studio PC", "USB drive"). Everything is stored in
`data/library.db` (SQLite) and reloaded at startup, so **restarting the app
never costs you a rescan**, and the library you had selected is still selected.

Libraries are fully independent: their tracks, their sources, and their
remembered version choices. That last one matters — the same song resolves to a
different file on each device, so a single shared list of choices would have
your devices overwriting each other. Deleting a library removes its scanned data
and choices; it never touches your music files.

Each library is built from one or more sources — a scanned folder, an imported
rekordbox XML, or several of each, merged and deduplicated by file path:

**Scan a folder.** Reads tags (and filenames, for untagged files) from every
audio file underneath, **including BPM and musical key when they are written
into the file** — rekordbox and Serato store key in ID3 `TKEY`, Mixed In Key
uses `TXXX:INITIALKEY`, and BPM lives in `TBPM` (MP4 `tmpo`, Vorbis `BPM` for
m4a/FLAC). Nonsense values (`0`, unparseable, out of a 20–300 range) are ignored
rather than stored. The first pass over a big folder takes a while; afterwards
each file is re-read only when its size or modification time changed, so repeat
scans take seconds. **Force rescan** ignores that and re-reads everything.

**Import a rekordbox XML export.** In rekordbox: `File › Export Collection in
xml format`. This is often the better source:

- it covers tracks on drives that aren't plugged in right now (you'll be told
  how many are currently missing — they still match, and rekordbox will find
  them once the drive is connected)
- it carries rekordbox's own analysed BPM and key, which beat whatever a tagger
  wrote into the file (and a later folder rescan will not take that back)
- it's near-instant, no matter how big the collection is
- rekordbox sometimes stores the version in a separate `Mix` field; that gets
  folded back into the title so the remix picker still works

## Most-played playlists

Upload rekordbox playlist exports — "Most played 2026", "Last month", "All
time" — per library, and the matcher uses them to work out which version of a
song you actually play. In rekordbox: right-click the playlist › Export. Any of
**m3u8, m3u, pls, txt or xml** works; m3u8 is the most reliable because it
carries file paths, while the TXT export has none and is resolved by artist and
title instead (at a stricter threshold, since a wrong resolution here would
quietly promote the wrong version later). Re-uploading a playlist of the same
name replaces it.

They do two things:

**Ranking, always.** A file that's in one of your playlists is offered first and
marked `★`, and being in several ranks higher still. This is deliberately a
nudge, not a veto: it settles a close call between two versions but never
outweighs a version or artist mismatch, so playing the radio edit constantly
won't make it stand in for the original a playlist asked for.

**Filtering, on demand.** Matching can be narrowed to a single playlist —
"which of this Spotify playlist do I have in my 2026 most-played" — with
everything outside it reported as not found. A file that appears in several
sources is stored once but claimed by each, so removing one source only drops
the tracks nothing else claims — and a folder rescan never blanks the BPM and
key that came from rekordbox, since a scan can't observe those.

## Matching notes

- **Files without tags** are matched by filename (`Artist - Title.mp3` patterns).
- **iTunes / Apple Music**: iTunes songs are `.m4a` files and fully supported
  (AAC and Apple Lossless). Typical folders: macOS
  `~/Music/Music/Media.localized/` (older: `~/Music/iTunes/iTunes Media/Music/`),
  Windows `C:\Users\<you>\Music\iTunes\iTunes Media\Music\`. **`.m4p` files**
  (pre-2010 iTunes purchases and Apple Music *subscription* downloads) are
  DRM-locked — rekordbox can't play them, so the scanner counts and reports them
  instead of matching them.
- **Playlists over ~100 tracks**: Spotify's public embed data stops around 100
  tracks. The API says so, and the paste-a-tracklist fallback has no cap.
- **Remembered versions** are keyed on artist + core title + version, so a
  choice survives whichever way the playlist was loaded (Spotify link or pasted
  text), and different versions stay independent: teaching it your favourite
  *Strobe* says nothing about *Strobe (Radio Edit)*. Featured artists are ignored
  in that key, because playlists list them inconsistently. Choices also survive
  removing a library source — if the file comes back, so does the preference.
  They are **per library**, so each device learns its own.

## Wedding couples (guest intake)

The API carries one record per couple, created with names + wedding date, which
issues two **magic links**:

- **Couple link** — the full eight-page intake: welcome, opening dance (with
  start preference and a note to the DJ), second & third song, their top 20, a
  reveal page, the friends' top 20, the never list, and the finale (up to five
  must-plays, a "how we party" briefing, pasted playlist links).
- **Friends link** — one shared link, scoped to the friends' top 20 only.
  Friends see each other's picks and fill the 20 spots together, but can't
  remove or reorder anything — and they see nothing else of the couple's answers.

Writes are idempotent so the intake app can retry on a flaky connection and
flush on tab close. Links stop working the day after the wedding and can be
**revoked** or **rotated** (new link, old one dies) at any time.

The **never list is a blocklist**: its songs (every version of them) are
stripped from every export for that couple, server-side. The change log records
which link each song came from (couple vs friends).

The UI for all of this is in the other two repos: `rekord-dj` has the DJ panel,
`rekord-couple` is what the guests open.

### Spotify song search for guests

The song fields in the intake are typeahead searches backed by Spotify's
official API via a **server-side proxy** — the secret never reaches a browser,
guests are rate-limited, repeated queries are cached, and only **metadata**
(title, artist, duration, ISRC, artwork URL) is ever fetched — no audio, ever.
Create a (free) app at <https://developer.spotify.com/dashboard> and provide its
credentials either as environment variables:

```bash
SPOTIFY_CLIENT_ID=...      SPOTIFY_CLIENT_SECRET=...
```

or in `data/spotify_credentials.json`:

```json
{ "client_id": "...", "client_secret": "..." }
```

Without credentials the intake still works — song fields simply save whatever
guests type, flagged "as typed", and the DJ resolves them at matching time.
Songs not on Spotify always have that same free-text fallback.

## Importing into rekordbox

**M3U8 (recommended):** rekordbox → `File › Import › Import Playlist` → pick the
downloaded `.m3u8`. Tracks already in your collection are matched by file path
(cues/grids untouched); new files are added and analyzed.

**Missing tracks (.txt):** not for rekordbox — a shopping list of the playlist's
tracks that aren't in the selected library. Plain `Artist - Title` lines so it
pastes straight into a shop's search box, with a couple of `#` comment lines for
context. Tracks nothing matched are listed under *Not found*; ones that had a
real match the DJ passed on are listed separately under *Skipped*, so the
buy-list stays honest.

**rekordbox XML:** `Preferences › Advanced › Database › rekordbox xml` → browse
to the downloaded `.rekordbox.xml`. Show the xml pane via `Preferences › View ›
Layout › rekordbox xml`. In the tree's *rekordbox xml* section, right-click the
playlist → `Import Playlist`.

## Checking the Spotify fetch

The playlist fetch uses Spotify's public embed page (the same trick "no sign-in"
converter sites use) because Spotify's official API stopped allowing anonymous
metadata access in 2026. Verify it works from your machine:

```bash
python scripts/probe_spotify.py "https://open.spotify.com/playlist/<id>"
```

`OK` + a track list means you're good. If Spotify changes their page format some
day, the app says so and the paste-text fallback always keeps working (plan B
for developers: swap `server/spotify/` for the `spotifyscraper` PyPI package
behind the same interface).

## Limitations (POC)

- Public playlists only (no Spotify login) — make a private playlist public for
  a minute, or paste it as text
- Embed data caps at ~100 tracks (reported by the API; text paste has no cap)
- Matching is metadata-only (tags/filenames/duration) — no audio fingerprinting
- The app reads your rekordbox collection but never writes to it; playlists come
  back as files you import
- `POST /api/scan` walks a **local** folder, so the scan/match half only makes
  sense where the music is. What genuinely belongs on a server is the couples
  intake, which is meant to be reached from someone else's phone.

## Troubleshooting

- **Folder not found**: quotes and trailing slashes are trimmed automatically;
  check the path and permissions. `~` works.
- **Wrong matches after retagging**: force a rescan, or re-import a fresh XML
  export.
- **Library looks stale**: re-import the XML (same filename replaces the old
  import) or rescan the folder.
- **Reset everything**: delete the `data/` folder.

## Development

```bash
.venv/bin/pytest    # parsers, scanner, database, libraries, playlists,
                    # matcher calibration, preferences, exports, API
```

The matching thresholds live in `server/matcher/score.py`;
`tests/test_matcher.py` is the calibration harness — tune, run, repeat.

Deployment for all three repos is driven from `deploy/` here — see
[docs/deploy.md](docs/deploy.md).
