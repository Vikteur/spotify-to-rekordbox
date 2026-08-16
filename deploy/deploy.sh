#!/usr/bin/env bash
# Runs ON the Hetzner box. CI scp's it in and calls it with the new image tag.
#
#   ./deploy.sh ghcr.io/vikteur/spotify-to-rekordbox:<sha>
#
# Switches APP_IMAGE, pulls, restarts, then health-checks. If the new image
# does not come up healthy it puts the previous one back and exits non-zero,
# so a bad merge does not leave the site down.
#
# The two front-end containers (DJ_IMAGE, COUPLE_IMAGE) are pulled and
# restarted alongside it. They are static nginx images with no state, so they
# are not part of the rollback: a bad API image is what can take the site
# down, and the front-ends are pinned in .env if one ever needs holding back.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/rekordmatch}"
NEW_IMAGE="${1:?usage: deploy.sh <image:tag>}"
HEALTH_RETRIES="${HEALTH_RETRIES:-30}"
HEALTH_DELAY="${HEALTH_DELAY:-2}"

cd "$APP_DIR"

if [[ ! -f .env ]]; then
	echo "FATAL: $APP_DIR/.env is missing — run bootstrap.sh first." >&2
	exit 1
fi

APP_PORT="$(grep -E '^APP_PORT=' .env | cut -d= -f2- || true)"
APP_PORT="${APP_PORT:-8000}"

set_image() {
	# Rewrite APP_IMAGE in place, appending it if it isn't there yet.
	if grep -qE '^APP_IMAGE=' .env; then
		sed -i "s|^APP_IMAGE=.*|APP_IMAGE=$1|" .env
	else
		printf 'APP_IMAGE=%s\n' "$1" >>.env
	fi
}

PREV_IMAGE="$(grep -E '^APP_IMAGE=' .env | cut -d= -f2- || true)"
echo "==> previous: ${PREV_IMAGE:-<none>}"
echo "==> new:      $NEW_IMAGE"

set_image "$NEW_IMAGE"

echo "==> pulling"
docker compose pull app dj couple

echo "==> starting"
docker compose up -d --remove-orphans

echo "==> waiting for /api/health on 127.0.0.1:$APP_PORT"
healthy=0
for ((i = 1; i <= HEALTH_RETRIES; i++)); do
	if curl -fsS --max-time 3 "http://127.0.0.1:${APP_PORT}/api/health" >/dev/null 2>&1; then
		healthy=1
		echo "==> healthy after ${i} attempt(s)"
		break
	fi
	sleep "$HEALTH_DELAY"
done

if [[ $healthy -ne 1 ]]; then
	echo "!!! new image never became healthy — logs follow" >&2
	docker compose logs --tail=80 app >&2 || true

	if [[ -n "$PREV_IMAGE" && "$PREV_IMAGE" != "$NEW_IMAGE" ]]; then
		echo "!!! rolling back to $PREV_IMAGE" >&2
		set_image "$PREV_IMAGE"
		docker compose up -d
	else
		echo "!!! no previous image to roll back to" >&2
	fi
	exit 1
fi

# The front-ends are not rolled back, but a dead one still means a dead site,
# so say so loudly rather than reporting a clean deploy.
DJ_PORT="$(grep -E '^DJ_PORT=' .env | cut -d= -f2- || true)"
COUPLE_PORT="$(grep -E '^COUPLE_PORT=' .env | cut -d= -f2- || true)"
for pair in "dj:${DJ_PORT:-8081}" "couple:${COUPLE_PORT:-8082}"; do
	name="${pair%%:*}"
	port="${pair##*:}"
	up=0
	for ((i = 1; i <= HEALTH_RETRIES; i++)); do
		if curl -fsS --max-time 3 "http://127.0.0.1:${port}/healthz" >/dev/null 2>&1; then
			up=1
			break
		fi
		sleep "$HEALTH_DELAY"
	done
	if [[ $up -ne 1 ]]; then
		echo "!!! the $name front-end never answered /healthz on :$port" >&2
		docker compose logs --tail=40 "$name" >&2 || true
		exit 1
	fi
	echo "==> $name healthy"
done

# Keep the disk from filling with every tag we have ever deployed.
docker image prune -af --filter "until=168h" >/dev/null 2>&1 || true

echo "==> deployed $NEW_IMAGE"
