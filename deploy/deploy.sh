#!/usr/bin/env bash
# deploy.sh — Déploiement sur VPS (Ubuntu/Debian)
# Usage: sudo bash deploy/deploy.sh
set -euo pipefail

APP_USER="paperbot"
APP_DIR="/opt/paper-btc-bot"
SERVICE_NAME="paper-btc-bot"

echo "==> Création de l'utilisateur dédié $APP_USER"
id "$APP_USER" &>/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_USER"

echo "==> Création du répertoire $APP_DIR"
mkdir -p "$APP_DIR"/{data,logs}

echo "==> Copie des fichiers projet"
rsync -a --exclude='.venv' --exclude='data/*.db' --exclude='.env' --exclude='__pycache__' ./ "$APP_DIR/"

echo "==> Création du venv Python"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "==> Initialisation de la base de données"
"$APP_DIR/.venv/bin/python" -m src.scripts.init_db

if [ ! -f "$APP_DIR/.env" ]; then
    echo "==> Copie du .env.example vers .env (à configurer !)"
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo "    ⚠️  Pensez à éditer $APP_DIR/.env avec vos tokens Telegram"
fi

echo "==> Droits"
chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
chmod 600 "$APP_DIR/.env"

echo "==> Installation du service systemd"
cp "$APP_DIR/deploy/paper-btc-bot.service" /etc/systemd/system/"$SERVICE_NAME".service
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"

echo "==> Vérification"
systemctl status "$SERVICE_NAME" --no-pager || true
echo ""
echo "✅ Déploiement terminé. Logs: journalctl -u $SERVICE_NAME -f"
