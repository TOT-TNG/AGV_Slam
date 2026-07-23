#!/usr/bin/env bash
# install_service_webui_linux.sh - Dang ky Web_UI (Dash dashboard, port 8050)
# chay nen nhu 1 systemd service, tu khoi dong cung may va tu restart neu
# crash. Dung chung venv da tao san o mqtt_Server/.venv (chay deploy/install.sh
# truoc neu chua co).
#
# Chay (can sudo):
#   sudo bash mqtt_Server/deploy/install_service_webui_linux.sh
#
# Go bo service:
#   sudo systemctl disable --now agv-webui
#   sudo rm /etc/systemd/system/agv-webui.service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MQTT_DIR="$(dirname "$SCRIPT_DIR")"          # mqtt_Server/
ROOT_DIR="$(dirname "$MQTT_DIR")"            # thu muc goc project
WEBUI_DIR="$ROOT_DIR/Web_UI"
UNIT_FILE="/etc/systemd/system/agv-webui.service"

if [ ! -x "$MQTT_DIR/.venv/bin/python3" ]; then
    echo "[SERVICE] Chua thay venv tai $MQTT_DIR/.venv - chay deploy/install.sh (mqtt_Server) truoc"
    exit 1
fi
if [ ! -f "$WEBUI_DIR/main.py" ]; then
    echo "[SERVICE] Khong tim thay $WEBUI_DIR/main.py"
    exit 1
fi

echo "[SERVICE] Tao $UNIT_FILE ..."
sed -e "s|__WEBUI_DIR__|$WEBUI_DIR|g" -e "s|__MQTT_DIR__|$MQTT_DIR|g" \
    "$SCRIPT_DIR/webui.service.template" | sudo tee "$UNIT_FILE" >/dev/null

echo "[SERVICE] Nap lai systemd + bat service ..."
sudo systemctl daemon-reload
sudo systemctl enable --now agv-webui

echo "[SERVICE] XONG - Web UI se tu chay cung may va tu restart neu crash."
echo "[SERVICE] Xem trang thai: sudo systemctl status agv-webui"
echo "[SERVICE] Xem log:        journalctl -u agv-webui -f"
