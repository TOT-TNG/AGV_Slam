#!/usr/bin/env bash
# install.sh — Cai dat AGVmqtt server tren Linux (Debian/Ubuntu).
# Chay:  bash mqtt_Server/deploy/install.sh          (giu lai du lieu AGV da luu)
#        bash mqtt_Server/deploy/install.sh --no-seed
#
# Can quyen sudo de cai goi he thong (python3, postgresql, mosquitto) neu chua co.
# Tren distro khac Debian/Ubuntu (khong co apt-get), tu cai 3 phan nay truoc
# roi chay thang: python3 deploy/setup.py

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"   # mqtt_Server/

echo "=== AGVmqtt install (Linux) ==="

if command -v apt-get >/dev/null 2>&1; then
    NEED_INSTALL=()
    command -v python3 >/dev/null 2>&1 || NEED_INSTALL+=(python3)
    dpkg -s python3-venv >/dev/null 2>&1 || NEED_INSTALL+=(python3-venv)
    dpkg -s python3-pip  >/dev/null 2>&1 || NEED_INSTALL+=(python3-pip)
    command -v psql      >/dev/null 2>&1 || NEED_INSTALL+=(postgresql postgresql-contrib)
    command -v mosquitto >/dev/null 2>&1 || NEED_INSTALL+=(mosquitto mosquitto-clients)

    if [ ${#NEED_INSTALL[@]} -gt 0 ]; then
        echo "[INSTALL] Can quyen sudo de cai: ${NEED_INSTALL[*]}"
        sudo apt-get update
        sudo apt-get install -y "${NEED_INSTALL[@]}"
    else
        echo "[INSTALL] Python3/PostgreSQL/Mosquitto da co san, bo qua"
    fi

    sudo systemctl enable --now postgresql 2>/dev/null || true
    sudo systemctl enable --now mosquitto  2>/dev/null || true
else
    echo "[INSTALL] Khong tim thay apt-get (khong phai Debian/Ubuntu)."
    echo "[INSTALL] Tu cai dat truoc: python3 (+venv,+pip), postgresql, mosquitto"
    echo "[INSTALL] Roi chay lai: python3 $SCRIPT_DIR/setup.py $*"
    exit 1
fi

echo ""
echo "[INSTALL] Ap dung cau hinh Mosquitto mac dinh (listener 1883 + anonymous) ..."
if [ -d /etc/mosquitto/conf.d ]; then
    sudo cp "$SCRIPT_DIR/mosquitto.conf.template" /etc/mosquitto/conf.d/agvmqtt.conf
    sudo systemctl restart mosquitto || true
    echo "[INSTALL] Da ghi /etc/mosquitto/conf.d/agvmqtt.conf va restart mosquitto"
else
    echo "[INSTALL] Khong tim thay /etc/mosquitto/conf.d — tu copy "
    echo "          $SCRIPT_DIR/mosquitto.conf.template vao dung vi tri cau hinh Mosquitto"
fi

echo ""
echo "[INSTALL] Chay setup.py de tao venv + cai package + khoi tao database ..."
python3 "$SCRIPT_DIR/setup.py" "$@"
