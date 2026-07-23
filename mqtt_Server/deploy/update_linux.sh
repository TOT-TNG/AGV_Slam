#!/usr/bin/env bash
# update_linux.sh - Cap nhat AGVmqtt server sau khi da cai dat lan dau (khong
# can lam lai buoc apt-get/tao venv/tao database tu dau). Dung khi code co
# thay doi (git pull ve) va can nap len 2 service dang chay san.
#
# Chay:
#   bash mqtt_Server/deploy/update_linux.sh
#
# Viec script nay lam:
#   1. git pull code moi nhat (neu thu muc goc la 1 git repo)
#   2. Cai lai requirements.txt vao venv da co san (chi cai goi thay doi/moi)
#   3. Ap dung lai schema_core.sql (an toan - CREATE TABLE IF NOT EXISTS,
#      khong mat du lieu) phong truong hop schema co them thay doi
#   4. Restart 2 systemd service agvmqtt + agv-webui (neu da cai, dung sudo)
#
# KHONG dong bo du lieu backup - neu can cap nhat du lieu (AGV/ban do moi...)
# tu may khac, dung rieng buoc "Phuc hoi tu backup" trong INSTALL_GUIDE.md.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MQTT_DIR="$(dirname "$SCRIPT_DIR")"          # mqtt_Server/
ROOT_DIR="$(dirname "$MQTT_DIR")"            # thu muc goc project
VENV_PYTHON="$MQTT_DIR/.venv/bin/python3"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "[UPDATE] Chua thay venv tai $MQTT_DIR/.venv - day la lan cai dat dau tien, chay deploy/install.sh truoc (khong dung script nay)."
    exit 1
fi

# -- 1. git pull (neu la git repo) --------------------------------------------
if [ -d "$ROOT_DIR/.git" ]; then
    echo "[UPDATE] git pull code moi nhat..."
    (cd "$ROOT_DIR" && git pull)
else
    echo "[UPDATE] Thu muc goc khong phai git repo - bo qua git pull. Neu ban cap nhat code bang cach copy file thu cong, hay copy truoc khi chay script nay."
fi

# -- 2. Cai lai requirements.txt vao venv co san ------------------------------
echo "[UPDATE] Cap nhat package trong venv..."
"$VENV_PYTHON" -m pip install -r "$MQTT_DIR/requirements.txt"

# -- 3. Ap dung lai schema_core.sql (an toan, khong mat du lieu) --------------
echo "[UPDATE] Ap dung lai schema_core.sql (CREATE TABLE IF NOT EXISTS - an toan)..."
PGHOST_="${PGHOST:-localhost}"
PGPORT_="${PGPORT:-5432}"
PGUSER_="${PGUSER:-postgres}"
PGDATABASE_="${PGDATABASE:-TOT_AGV}"
if command -v psql >/dev/null 2>&1; then
    PGPASSWORD="${PGPASSWORD:-}" psql -h "$PGHOST_" -p "$PGPORT_" -U "$PGUSER_" -d "$PGDATABASE_" \
        -f "$SCRIPT_DIR/schema_core.sql"
else
    echo "[UPDATE] Khong tim thay lenh psql - bo qua buoc schema. Cai postgresql-client neu can chay buoc nay."
fi

# -- 4. Restart 2 systemd service (neu da cai) --------------------------------
for svc in agvmqtt agv-webui; do
    if systemctl list-unit-files | grep -q "^${svc}\.service"; then
        echo "[UPDATE] Restart service '$svc' ..."
        sudo systemctl restart "$svc"
        sleep 2
        sudo systemctl status "$svc" --no-pager -l | head -5
    else
        echo "[UPDATE] Service '$svc' chua duoc cai - bo qua restart (chay deploy/install_service_linux.sh / install_service_webui_linux.sh neu muon cai service)."
    fi
done

echo ""
echo "[UPDATE] HOAN TAT."
