#!/usr/bin/env bash
# install_service_linux.sh - Dang ky AGVmqtt server chay nen nhu 1 systemd
# service, tu khoi dong cung may va tu restart neu crash (Restart=always).
#
# Chay (can sudo):
#   sudo bash mqtt_Server/deploy/install_service_linux.sh
#
# Go bo service:
#   sudo systemctl disable --now agvmqtt
#   sudo rm /etc/systemd/system/agvmqtt.service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"    # mqtt_Server/
UNIT_FILE="/etc/systemd/system/agvmqtt.service"

if [ ! -x "$ROOT_DIR/.venv/bin/python3" ]; then
    echo "[SERVICE] Chua thay venv tai $ROOT_DIR/.venv - chay deploy/setup.py truoc"
    exit 1
fi

echo "[SERVICE] Tao $UNIT_FILE ..."
sed "s|__ROOT_DIR__|$ROOT_DIR|g" "$SCRIPT_DIR/agvmqtt.service.template" | sudo tee "$UNIT_FILE" >/dev/null

echo "[SERVICE] Nap lai systemd + bat service ..."
sudo systemctl daemon-reload
sudo systemctl enable --now agvmqtt

echo "[SERVICE] XONG - server se tu chay cung may va tu restart neu crash."
echo "[SERVICE] Xem trang thai: sudo systemctl status agvmqtt"
echo "[SERVICE] Xem log:        journalctl -u agvmqtt -f"
