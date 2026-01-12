#!/usr/bin/env bash
set -euo pipefail

# ---- CONFIG (edit these) ----
APP_NAME="myapp"
APP_USER="${SUDO_USER:-$USER}"                  # user to run services as
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"    # project root
BACKEND_PORT="8000"                             # only used for description/log sanity
FRONTEND_PORT="3000"                            # static server port
# -----------------------------

echo "[1/6] Installing OS packages..."
apt-get update -y
apt-get install -y npm python3-venv

echo "[2/6] Creating Python venv + installing backend deps..."
cd "$PROJECT_DIR"
python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
deactivate

echo "[3/6] Installing frontend deps + building..."
cd "$PROJECT_DIR/frontend"
npm install
npm run build

echo "[4/6] Installing frontend static server (serve)..."
# Use a global install so systemd can call it reliably
npm install -g serve

echo "[5/6] Writing systemd unit files..."
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
# Optional hardening:
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

tee "$FRONTEND_UNIT_PATH" >/dev/null <<EOF
[Unit]
Description=${APP_NAME} Frontend (serve React build)
After=network.target

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${PROJECT_DIR}/frontend
ExecStart=/usr/bin/env serve -s ${PROJECT_DIR}/frontend/build -l ${FRONTEND_PORT}
Restart=always
RestartSec=2
# Optional hardening:
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

echo "[6/6] Enabling + starting services..."
systemctl daemon-reload
systemctl enable --now "${APP_NAME}-backend.service"
systemctl enable --now "${APP_NAME}-frontend.service"

echo
echo "Done."
echo "Backend service:  ${APP_NAME}-backend.service  (expected port: ${BACKEND_PORT} if your app uses it)"
echo "Frontend service: ${APP_NAME}-frontend.service (serving build/ on port ${FRONTEND_PORT})"
echo
echo "Useful commands:"
echo "  systemctl status ${APP_NAME}-backend.service"
echo "  systemctl status ${APP_NAME}-frontend.service"
echo "  journalctl -u ${APP_NAME}-backend.service -f"
echo "  journalctl -u ${APP_NAME}-frontend.service -f"
