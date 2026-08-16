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

echo "==> nginx config installer"
# CI ships deploy/nginx/rekord.conf to $APP_DIR, but the deploy user cannot
# write /etc/nginx. Rather than hand it broad sudo, install one root-owned
# script it may run and may not edit. The script takes no arguments — the
# source path is fixed below — so the grant cannot be pointed at another file.
if command -v nginx >/dev/null 2>&1; then
	command -v sudo >/dev/null 2>&1 || apt-get install -y sudo

	cat >/usr/local/sbin/rekord-nginx-install <<'INSTALLER'
#!/usr/bin/env bash
# Installs the nginx site config CI uploaded. Written by bootstrap.sh.
set -euo pipefail

SRC="__APP_DIR__/rekord.conf"
DEST=/etc/nginx/sites-available/rekord
LINK=/etc/nginx/sites-enabled/rekord

[[ -f $SRC ]] || { echo "nothing to install: $SRC is missing" >&2; exit 1; }

if [[ -f $DEST ]] && cmp -s "$SRC" "$DEST"; then
	ln -sfn "$DEST" "$LINK"
	echo "nginx config unchanged"
	exit 0
fi

BACKUP=""
if [[ -f $DEST ]]; then
	BACKUP="$DEST.bak"
	cp -p "$DEST" "$BACKUP"
fi

install -o root -g root -m 644 "$SRC" "$DEST"
ln -sfn "$DEST" "$LINK"

# -t checks every site on the box, so a failure here can be someone else's
# config. Either way we put ours back the way we found it before bailing.
if ! nginx -t; then
	echo "nginx -t failed — rolling back" >&2
	if [[ -n $BACKUP ]]; then
		cp -p "$BACKUP" "$DEST"
	else
		rm -f "$DEST" "$LINK"
	fi
	nginx -t >/dev/null 2>&1 ||
		echo "WARNING: nginx config still fails to parse after rollback" >&2
	exit 1
fi

systemctl reload nginx
echo "nginx config installed and reloaded"
INSTALLER

	sed -i "s|__APP_DIR__|$APP_DIR|" /usr/local/sbin/rekord-nginx-install
	chown root:root /usr/local/sbin/rekord-nginx-install
	chmod 755 /usr/local/sbin/rekord-nginx-install

	printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/rekord-nginx-install\n' \
		"$DEPLOY_USER" >/etc/sudoers.d/rekord-nginx
	chmod 440 /etc/sudoers.d/rekord-nginx
	if ! visudo -cf /etc/sudoers.d/rekord-nginx >/dev/null; then
		rm -f /etc/sudoers.d/rekord-nginx
		echo "FATAL: refused to keep a sudoers file that does not parse" >&2
		exit 1
	fi
	echo "    /usr/local/sbin/rekord-nginx-install (+ sudo grant for $DEPLOY_USER)"
else
	echo "    nginx not installed — skipping (using the bundled Caddy instead?)"
fi

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
