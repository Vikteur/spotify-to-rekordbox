from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="spotify-to-rekordbox")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


# When the client has been built (npm run build), serve it so the whole app
# runs from uvicorn alone. Mounted last so /api routes take precedence.
DIST = Path(__file__).resolve().parent.parent / "dist"
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="static")
