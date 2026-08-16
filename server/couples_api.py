"""HTTP routes for the wedding-couple intake.

Two audiences share this router:

- **DJ routes** (`/api/couples...`) — the local, single-user side. Create a
  couple, read everything as it streams in, manage the two magic links.
- **Guest routes** (`/api/guest/{token}...`) — what the couple and their
  friends reach through a magic link. The token in the path *is* the
  authentication; scope comes from which of the couple's two tokens matched:

    couple token   read/write the whole couple record
    friends token  append to the friends' top 20, read only that list

  Friends deliberately cannot delete, edit others' rows or reorder anything —
  one shared link must not let a guest shuffle everyone else's picks.
"""

import sqlite3

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server import couples
from server.spotify import search as spotify_search

router = APIRouter()


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _domain_error(exc: couples.CoupleError) -> HTTPException:
    status = {"LIST_FULL": 409, "UID_CONFLICT": 409, "UNKNOWN_ENTRY": 404}.get(exc.code, 400)
    return _error(status, exc.code, str(exc))


def _entry_label(entry: dict) -> str:
    artist = (entry.get("artist") or "").strip()
    title = (entry.get("title") or "").strip()
    return f"{artist} – {title}" if artist else title


# --- request bodies ---------------------------------------------------------

class CoupleCreate(BaseModel):
    names: str
    wedding_date: str


class CoupleUpdate(BaseModel):
    names: str | None = None
    wedding_date: str | None = None
    briefing_text: str | None = None


class RevokeRequest(BaseModel):
    revoked: bool = True


class EntryIn(BaseModel):
    kind: str
    position: int | None = None
    spotify_id: str | None = None
    isrc: str | None = None
    title: str = ""
    artist: str = ""
    duration_ms: int | None = None
    art_url: str | None = None
    free_text: str | None = None
    note: str | None = None
    start_pref: str | None = None


class BlockIn(BaseModel):
    spotify_id: str | None = None
    isrc: str | None = None
    title: str = ""
    artist: str = ""
    duration_ms: int | None = None
    art_url: str | None = None
    free_text: str | None = None


class OrderIn(BaseModel):
    positions: list[dict]  # [{uid, position}]


# --- payload builders -------------------------------------------------------

def _couple_detail(couple: sqlite3.Row) -> dict:
    """Everything the DJ sees for one couple, tokens included (local app)."""
    return {
        "id": couple["id"],
        "names": couple["names"],
        "wedding_date": couple["wedding_date"],
        "briefing_text": couple["briefing_text"],
        "created_at": couple["created_at"],
        "links": {
            kind: {
                "token": couple[f"{column}_token"],
                "path": f"/g/{couple[f'{column}_token']}",
                "revoked": bool(couple[f"{column}_revoked"]),
                "expired": couples.token_expired(couple),
            }
            for kind, column in (("couple", "couple"), ("friends", "friends"))
        },
        "lists": couples.list_entries(couple["id"]),
        "blocklist": couples.list_blocklist(couple["id"]),
        "changes": couples.list_changes(couple["id"], limit=30),
    }


def _guest_payload(couple: sqlite3.Row, scope: str) -> dict:
    base = {
        "scope": scope,
        "names": couple["names"],
        "wedding_date": couple["wedding_date"],
        "caps": couples.LIST_KINDS,
        "search_available": spotify_search.is_configured(),
    }
    if scope == "friends":
        base["entries"] = couples.list_entries(couple["id"], "friends_top20")
        return base
    base["briefing_text"] = couple["briefing_text"]
    base["entries"] = couples.list_entries(couple["id"])
    base["blocklist"] = couples.list_blocklist(couple["id"])
    # The couple's screen 6 shows the link they hand to their friends.
    base["friends_link"] = f"/g/{couple['friends_token']}"
    return base


# --- DJ routes --------------------------------------------------------------

@router.post("/api/couples", status_code=201)
def create_couple(request: CoupleCreate) -> dict:
    try:
        couple_id = couples.create_couple(request.names, request.wedding_date)
    except couples.CoupleError as exc:
        raise _domain_error(exc)
    return _couple_detail(couples.get_couple(couple_id))


@router.get("/api/couples")
def get_couples() -> dict:
    return {"couples": couples.list_couples()}


def _require_couple(couple_id: int) -> sqlite3.Row:
    couple = couples.get_couple(couple_id)
    if couple is None:
        raise _error(404, "NO_COUPLE", f"No couple with id {couple_id}.")
    return couple


@router.get("/api/couples/{couple_id}")
def get_couple(couple_id: int) -> dict:
    return _couple_detail(_require_couple(couple_id))


@router.patch("/api/couples/{couple_id}")
def update_couple(couple_id: int, request: CoupleUpdate) -> dict:
    _require_couple(couple_id)
    try:
        couples.update_couple(
            couple_id,
            names=request.names,
            wedding_date=request.wedding_date,
            briefing_text=request.briefing_text,
        )
    except couples.CoupleError as exc:
        raise _domain_error(exc)
    return _couple_detail(couples.get_couple(couple_id))


@router.delete("/api/couples/{couple_id}")
def delete_couple(couple_id: int) -> dict:
    if not couples.delete_couple(couple_id):
        raise _error(404, "NO_COUPLE", f"No couple with id {couple_id}.")
    return {"couples": couples.list_couples()}


@router.post("/api/couples/{couple_id}/tokens/{token_kind}/rotate")
def rotate_token(couple_id: int, token_kind: str) -> dict:
    _require_couple(couple_id)
    try:
        couples.rotate_token(couple_id, token_kind)
    except couples.CoupleError as exc:
        raise _domain_error(exc)
    couples.log_change(couple_id, "dj", "details", f"rotated the {token_kind} link")
    return _couple_detail(couples.get_couple(couple_id))


@router.post("/api/couples/{couple_id}/tokens/{token_kind}/revoke")
def revoke_token(couple_id: int, token_kind: str, request: RevokeRequest) -> dict:
    _require_couple(couple_id)
    try:
        couples.set_revoked(couple_id, token_kind, request.revoked)
    except couples.CoupleError as exc:
        raise _domain_error(exc)
    verb = "revoked" if request.revoked else "re-enabled"
    couples.log_change(couple_id, "dj", "details", f"{verb} the {token_kind} link")
    return _couple_detail(couples.get_couple(couple_id))


@router.get("/api/couples/{couple_id}/changes")
def get_changes(couple_id: int, limit: int = 100) -> dict:
    _require_couple(couple_id)
    return {"changes": couples.list_changes(couple_id, limit=min(limit, 500))}


# --- guest routes -----------------------------------------------------------

def _resolve_token(token: str) -> tuple[sqlite3.Row, str]:
    found = couples.find_by_token(token)
    if found is None:
        raise _error(404, "BAD_LINK", "This link isn't valid. Ask your DJ for a fresh one.")
    couple, scope = found
    revoked = couple["couple_revoked" if scope == "couple" else "friends_revoked"]
    if revoked:
        raise _error(403, "LINK_REVOKED", "This link was switched off. Ask your DJ for a new one.")
    if couples.token_expired(couple):
        raise _error(
            410, "LINK_EXPIRED",
            "This link expired after the wedding. Congratulations again!",
        )
    return couple, scope


@router.get("/api/guest/{token}")
def guest_state(token: str) -> dict:
    couple, scope = _resolve_token(token)
    return _guest_payload(couple, scope)


@router.patch("/api/guest/{token}/couple")
def guest_update_couple(token: str, request: CoupleUpdate) -> dict:
    couple, scope = _resolve_token(token)
    if scope != "couple":
        raise _error(403, "FORBIDDEN", "Only the couple can change these details.")
    try:
        couples.update_couple(
            couple["id"],
            names=request.names,
            wedding_date=request.wedding_date,
            briefing_text=request.briefing_text,
        )
    except couples.CoupleError as exc:
        raise _domain_error(exc)
    changed = [
        label
        for label, value in (
            ("names", request.names),
            ("wedding date", request.wedding_date),
            ("the “how we party” note", request.briefing_text),
        )
        if value is not None
    ]
    if changed:
        couples.log_change(couple["id"], scope, "details", f"updated {', '.join(changed)}")
    return _guest_payload(couples.get_couple(couple["id"]), scope)


def _guard_friend_write(scope: str, kind: str, uid: str) -> None:
    """What one shared friends link may do: add to the friends list, touch
    nothing else, and only re-save rows that came from a friend."""
    if scope != "friends":
        return
    if kind != "friends_top20":
        raise _error(403, "FORBIDDEN", "This link can only add to the friends' top 20.")
    existing = couples.entry_owner(uid)
    if existing is not None and existing["source_token_kind"] != "friend":
        raise _error(403, "FORBIDDEN", "That row belongs to the couple.")


@router.put("/api/guest/{token}/entries/{uid}")
def guest_put_entry(token: str, uid: str, request: EntryIn) -> dict:
    couple, scope = _resolve_token(token)
    _guard_friend_write(scope, request.kind, uid)
    token_kind = "couple" if scope == "couple" else "friend"
    created = couples.entry_owner(uid) is None
    try:
        entry = couples.upsert_entry(couple["id"], uid, request.model_dump(), token_kind)
    except couples.CoupleError as exc:
        raise _domain_error(exc)
    label = couples.LIST_LABELS.get(request.kind, request.kind)
    couples.log_change(
        couple["id"], token_kind, "added" if created else "updated",
        f"{'added' if created else 'updated'} “{_entry_label(entry)}” in {label}",
        kind=request.kind, uid=uid,
    )
    return {"entry": entry, "entries": couples.list_entries(couple["id"], request.kind)}


@router.delete("/api/guest/{token}/entries/{uid}")
def guest_delete_entry(token: str, uid: str) -> dict:
    couple, scope = _resolve_token(token)
    if scope != "couple":
        raise _error(403, "FORBIDDEN", "Only the couple can remove songs.")
    removed = couples.delete_entry(couple["id"], uid)
    if removed is None:
        # Deleting what's already gone is a successful no-op (autosave retries).
        return {"entries": couples.list_entries(couple["id"])}
    label = couples.LIST_LABELS.get(removed["kind"], removed["kind"])
    couples.log_change(
        couple["id"], "couple", "removed",
        f"removed “{_entry_label(removed)}” from {label}",
        kind=removed["kind"], uid=uid,
    )
    return {"entries": couples.list_entries(couple["id"], removed["kind"])}


@router.put("/api/guest/{token}/order/{kind}")
def guest_reorder(token: str, kind: str, request: OrderIn) -> dict:
    couple, scope = _resolve_token(token)
    if scope != "couple":
        raise _error(403, "FORBIDDEN", "Only the couple can reorder the lists.")
    try:
        couples.reorder(couple["id"], kind, request.positions)
    except couples.CoupleError as exc:
        raise _domain_error(exc)
    label = couples.LIST_LABELS.get(kind, kind)
    couples.log_change(couple["id"], "couple", "reordered", f"reordered {label}", kind=kind)
    return {"entries": couples.list_entries(couple["id"], kind)}


@router.put("/api/guest/{token}/blocklist/{uid}")
def guest_put_block(token: str, uid: str, request: BlockIn) -> dict:
    couple, scope = _resolve_token(token)
    if scope != "couple":
        raise _error(403, "FORBIDDEN", "Only the couple can edit the never list.")
    created = True
    try:
        existing = {entry["uid"] for entry in couples.list_blocklist(couple["id"])}
        created = uid not in existing
        entry = couples.upsert_block(couple["id"], uid, request.model_dump(), "couple")
    except couples.CoupleError as exc:
        raise _domain_error(exc)
    couples.log_change(
        couple["id"], "couple", "added" if created else "updated",
        f"{'added' if created else 'updated'} “{_entry_label(entry)}” on the never list",
        kind="never", uid=uid,
    )
    return {"entry": entry, "blocklist": couples.list_blocklist(couple["id"])}


@router.delete("/api/guest/{token}/blocklist/{uid}")
def guest_delete_block(token: str, uid: str) -> dict:
    couple, scope = _resolve_token(token)
    if scope != "couple":
        raise _error(403, "FORBIDDEN", "Only the couple can edit the never list.")
    removed = couples.delete_block(couple["id"], uid)
    if removed is not None:
        couples.log_change(
            couple["id"], "couple", "removed",
            f"took “{_entry_label(removed)}” off the never list",
            kind="never", uid=uid,
        )
    return {"blocklist": couples.list_blocklist(couple["id"])}


@router.get("/api/guest/{token}/search")
def guest_search(token: str, q: str = "") -> dict:
    _resolve_token(token)
    if not q.strip():
        return {"results": []}
    try:
        results = spotify_search.search_tracks(q, limiter_key=token)
    except spotify_search.SearchRateLimited as exc:
        raise _error(429, "RATE_LIMITED", str(exc))
    except spotify_search.SearchUnavailable as exc:
        raise _error(503, "SEARCH_UNAVAILABLE", str(exc))
    return {"results": results}
