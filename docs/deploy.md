# Deploying to Hetzner

Merge to `main` → GitHub Actions runs the tests, builds one Docker image,
pushes it to GHCR, SSHes into the Hetzner box and restarts the container there.
If the new image doesn't answer `/api/health`, the previous one goes back up
automatically and the run fails red.

```
merge to main
  └─ test    pytest (232 tests) + tsc --noEmit + vite build
  └─ build   docker build → ghcr.io/vikteur/spotify-to-rekordbox:<sha>
  └─ deploy  scp compose+script → ssh → pull → up -d → health-check
                                                  └─ unhealthy? roll back
```

## What actually runs on the server

**One container.** `server/main.py` mounts the built client (`dist/`) as static
files, so uvicorn serves the API *and* the React app on port 8000. There is no
separate web service to deploy.

It publishes on `127.0.0.1:8000` only — nothing from the internet reaches it
except through a reverse proxy on the same box.

**State lives in a Docker volume** (`rekordmatch_data` → `/app/data`). That's
`library.db`: libraries, imported playlists, couples, magic-link tokens.
Deploys replace the container, never the volume. It is *not* in git and *not*
in the image — back it up (see below).

## One-time setup

### 1. The server

```bash
scp deploy/bootstrap.sh root@YOUR_SERVER_IP:/tmp/
ssh root@YOUR_SERVER_IP "bash /tmp/bootstrap.sh"
```

Idempotent — installs Docker only if missing, creates the `deploy` user,
opens 80/443, creates `/opt/rekordmatch`.

### 2. A key for CI

On your machine:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/rekordmatch_deploy -C "github-actions" -N ""
ssh-copy-id -i ~/.ssh/rekordmatch_deploy.pub deploy@YOUR_SERVER_IP
ssh-keyscan -H YOUR_SERVER_IP          # → paste into SSH_KNOWN_HOSTS
cat ~/.ssh/rekordmatch_deploy          # → paste into SSH_PRIVATE_KEY
```

### 3. Repo secrets

`Settings → Secrets and variables → Actions`:

| Secret | Value | Required |
|---|---|---|
| `HETZNER_HOST` | server IP or hostname | yes |
| `HETZNER_USER` | `deploy` | yes |
| `SSH_PRIVATE_KEY` | the whole private key, incl. BEGIN/END lines | yes |
| `SSH_KNOWN_HOSTS` | `ssh-keyscan` output | recommended |
| `APP_DIR` | defaults to `/opt/rekordmatch` | no |

`GITHUB_TOKEN` is automatic — no PAT needed, the server logs in to GHCR with
the workflow's own token.

### 4. The server's `.env`

```bash
scp deploy/.env.example deploy@YOUR_SERVER_IP:/opt/rekordmatch/.env
ssh deploy@YOUR_SERVER_IP "chmod 600 /opt/rekordmatch/.env && nano /opt/rekordmatch/.env"
```

Set the domain and Spotify keys. CI rewrites `APP_IMAGE` on every deploy;
leave the rest alone.

### 5a. If the box already runs nginx (this one does)

`46.224.211.159` already serves `viktorvansteenweghen.com` through system
nginx on 80/443, so the bundled Caddy stays **off** — it would fail to bind.
Leave `COMPOSE_PROFILES` commented and use `deploy/nginx/rekord.conf` instead:
same allow-list, nginx syntax.

```bash
scp deploy/nginx/rekord.conf root@SERVER:/etc/nginx/sites-available/rekord
ssh root@SERVER "ln -sfn /etc/nginx/sites-available/rekord /etc/nginx/sites-enabled/rekord && nginx -t && systemctl reload nginx"
```

The password file is nginx's own format, not Caddy's bcrypt:

```bash
ssh root@SERVER "printf 'dj:%s\n' \"\$(openssl passwd -apr1 'your-password')\" > /etc/nginx/.htpasswd-rekord
                 chmod 640 /etc/nginx/.htpasswd-rekord && chown root:www-data /etc/nginx/.htpasswd-rekord"
```

Note `nginx -t` before every reload — a bad config fails the test and leaves
the running nginx untouched, so the other sites on the box stay up.

### 5b. TLS and the DJ password (bundled Caddy)

Uncomment `COMPOSE_PROFILES=proxy` and `APP_DOMAIN` in `.env` to use the
bundled Caddy — it gets a Let's Encrypt cert on first boot, provided the A
record already points at the box. Already running nginx or Traefik? Leave
those commented, point your existing proxy at `127.0.0.1:8000`, and copy the
auth rules below into its config.

Then set the password:

```bash
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'your-password'
```

Paste the hash into `.env` as `DJ_PASSWORD_HASH` **with every `$` doubled**
(`$2a$14$...` → `$$2a$$14$$...`). Compose interpolates the env file, so a single
`$` is swallowed and the login fails with no useful error.

Then merge to `main`.

## Who can reach what

The app has no login of its own — it was written as a single-user local tool,
and `_couple_detail` (`server/couples_api.py:91`) returns both magic-link
tokens for a couple to anyone who asks. Couple IDs are sequential integers, so
on a public domain that is an open door: enumerate `/api/couples`, read every
token, `DELETE` any couple. Caddy closes it.

Open, no password — a guest on their phone needs these:

| Path | Why |
|---|---|
| `/g/*` | the magic-link page |
| `/api/guest/*` | guest API — the token in the path *is* the auth |
| `/assets/*` | the JS/CSS bundle the page loads |
| `/api/health` | uptime monitoring; returns only `{"ok":true}` |

Everything else — the DJ UI, `/api/couples`, `/api/library`, `/api/scan`,
`/api/match`, `/api/export`, `/api/preferences` — returns **401** without the
password.

`/g/*` also gets `Referrer-Policy: no-referrer`, so a guest tapping through to
Spotify can't leak their magic link in a `Referer` header.

Verified against the real containers: every DJ route 401s unauthenticated,
every guest route serves, and the password lets the DJ UI through.

## Day-to-day

```bash
ssh deploy@YOUR_SERVER_IP
cd /opt/rekordmatch

docker compose ps                  # what's up
docker compose logs -f app         # tail logs
docker compose restart app         # kick it
curl localhost:8000/api/health     # {"ok":true}
```

**Roll back by hand** — every deployed sha is still in GHCR:

```bash
./deploy.sh ghcr.io/vikteur/spotify-to-rekordbox:<older-sha>
```

**Back up the database** — a consistent copy, safe to take while the app is
running (`.backup` takes SQLite's own lock; a plain `cp` of a live DB can tear):

```bash
docker compose exec -T app python -c "import sqlite3; s=sqlite3.connect('/app/data/library.db'); d=sqlite3.connect('/app/data/backup.db'); s.backup(d); d.close(); s.close()"
docker compose cp app:/app/data/backup.db ./library-$(date +%F).db
docker compose exec -T app rm /app/data/backup.db
```

Worth a weekly cron — the magic-link tokens live in there, and regenerating
them means re-sending every couple their link.

## Known limitation

`POST /api/scan` walks a **local folder** of audio files and exports playlists
containing local paths. On a remote server there is no music folder, so the
scan/match half of the app is effectively local-only. What genuinely belongs
on this box is the couples intake and the `/g/<token>` guest magic links —
those are meant to be reached from someone else's phone.
