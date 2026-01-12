#!/usr/bin/env bash
set -euo pipefail

# ---- CONFIG (edit these) ----
APP_NAME="myapp"
APP_USER="${SUDO_USER:-$USER}"                  # user to run services as
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"    # project root
FRONTEND_PORT="3000"
# -----------------------------

echo "[1/6] Installing OS packages..."
apt-get update -y
apt-get install -y python3-venv nodejs npm

echo "[2/6] Creating Python venv + installing backend deps..."
cd "$PROJECT_DIR"
python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
deactivate

echo "[3/6] Installing frontend deps + building (Next.js)..."
cd "$PROJECT_DIR/frontend"
npm install
npm run build

echo "[4/6] Writing systemd unit files..."
BACKEND_UNIT_PATH="/etc/systemd/system/${APP_NAME}-backend.service"
FRONTEND_UNIT_PATH="/etc/systemd/system/${APP_NAME}-frontend.service"

tee "$BACKEND_UNIT_PATH" >/dev/null <<EOF
[Unit]
Description=${APP_NAME} Backend (python backend/server.py)
After=network.target

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${PROJECT_DIR}
Environment=PATH=${PROJECT_DIR}/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=${PROJECT_DIR}/venv/bin/python ${PROJECT_DIR}/backend/server.py
Restart=always
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# Next.js should be served with "next start" (via "npm run start"),
# NOT with a static server pointed at build/.
tee "$FRONTEND_UNIT_PATH" >/dev/null <<EOF
[Unit]
Description=${APP_NAME} Frontend (Next.js - npm run start)
After=network.target

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${PROJECT_DIR}/frontend
Environment=NODE_ENV=production
Environment=PORT=${FRONTEND_PORT}
ExecStart=/usr/bin/npm run start
Restart=always
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

echo "[5/6] Enabling + starting services..."
systemctl daemon-reload
systemctl enable --now "${APP_NAME}-backend.service"
systemctl enable --now "${APP_NAME}-frontend.service"

echo "[6/6] Status / logs helpers"
echo
echo "Frontend expected at: http://<host>:${FRONTEND_PORT}"
echo
echo "Check status:"
echo "  systemctl status ${APP_NAME}-backend.service"
echo "  systemctl status ${APP_NAME}-frontend.service"
echo
echo "Follow logs:"
echo "  journalctl -u ${APP_NAME}-backend.service -f"
echo "  journalctl -u ${APP_NAME}-frontend.service -f"
