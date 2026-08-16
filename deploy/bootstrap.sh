#!/usr/bin/env bash
# One-time server setup. Safe to re-run: every step checks before it acts.
#
#   scp deploy/bootstrap.sh root@SERVER:/tmp/ && ssh root@SERVER "bash /tmp/bootstrap.sh"
#
# Creates the deploy user, installs Docker if it isn't there, opens the
# firewall, and lays down $APP_DIR so CI has somewhere to land.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/rekordmatch}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"

[[ $EUID -eq 0 ]] || { echo "run this as root" >&2; exit 1; }

echo "==> deploy user: $DEPLOY_USER"
if ! id -u "$DEPLOY_USER" >/dev/null 2>&1; then
	adduser --disabled-password --gecos "" "$DEPLOY_USER"
else
	echo "    already exists"
fi

echo "==> docker"
if ! command -v docker >/dev/null 2>&1; then
	apt-get update
	apt-get install -y ca-certificates curl gnupg
	install -m 0755 -d /etc/apt/keyrings
	curl -fsSL https://download.docker.com/linux/ubuntu/gpg |
		gpg --dearmor -o /etc/apt/keyrings/docker.gpg
	chmod a+r /etc/apt/keyrings/docker.gpg
	echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
		>/etc/apt/sources.list.d/docker.list
	apt-get update
	apt-get install -y docker-ce docker-ce-cli containerd.io \
		docker-buildx-plugin docker-compose-plugin
else
	echo "    already installed: $(docker --version)"
fi
systemctl enable --now docker

# curl is what deploy.sh health-checks with.
command -v curl >/dev/null 2>&1 || apt-get install -y curl

echo "==> docker group"
usermod -aG docker "$DEPLOY_USER"

echo "==> $APP_DIR"
mkdir -p "$APP_DIR"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"

echo "==> ssh key for CI"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
touch "/home/$DEPLOY_USER/.ssh/authorized_keys"
chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
chown "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh/authorized_keys"

echo "==> firewall"
if command -v ufw >/dev/null 2>&1; then
	ufw allow OpenSSH
	ufw allow 80/tcp
	ufw allow 443/tcp
	ufw --force enable
	ufw status
else
	echo "    ufw not installed — skipping (check your Hetzner Cloud firewall instead)"
fi

cat <<NEXT

Bootstrap done.

Still to do, once:
  1. Put CI's public key in /home/$DEPLOY_USER/.ssh/authorized_keys
  2. Create $APP_DIR/.env from deploy/.env.example (fill in the domain + secrets)
  3. Merge to main — the pipeline takes it from there.

NEXT
