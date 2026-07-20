#!/usr/bin/env python3
"""
setup.py — Cai dat AGVmqtt server (da nen tang Windows/Linux).

Chay:  python deploy/setup.py            (giu lai du lieu AGV da luu)
       python deploy/setup.py --no-seed  (DB hoan toan trong)

Viec script nay lam:
  1. Tao Python virtualenv tai mqtt_Server/.venv (neu chua co)
  2. Cai cac goi trong requirements.txt vao venv do
  3. Tao database (bien PGDATABASE, mac dinh TOT_AGV) neu chua co
  4. Ap dung schema_core.sql (2 bang agv_devices/agv_tasks ma app khong tu tao)
  5. (mac dinh) Nap seed_agv_devices.sql — giu lai danh sach AGV da cau hinh
  6. Ghi mqtt_mode.json = local

KHONG tu cai Python/PostgreSQL/Mosquitto — dung install.sh (Linux) hoac
install.bat (Windows) de cai cac phan do truoc, hoac tu cai thu cong.

Bien moi truong co the ghi de: PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE.
"""
import os
import sys
import subprocess
import venv as venv_module
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent    # mqtt_Server/
DEPLOY_DIR = Path(__file__).resolve().parent      # mqtt_Server/deploy/
VENV_DIR = ROOT / ".venv"

IS_WINDOWS = os.name == "nt"
VENV_PYTHON = VENV_DIR / ("Scripts/python.exe" if IS_WINDOWS else "bin/python3")


def _run(cmd, **kw):
    print(f"$ {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, check=True, **kw)


def phase1_create_venv_and_install():
    if not VENV_DIR.exists():
        print(f"[SETUP] Tao virtualenv tai {VENV_DIR} ...")
        venv_module.EnvBuilder(with_pip=True).create(str(VENV_DIR))
    else:
        print(f"[SETUP] Virtualenv da ton tai tai {VENV_DIR}, bo qua buoc tao")

    req_file = ROOT / "requirements.txt"
    print(f"[SETUP] Cai goi tu {req_file} ...")
    _run([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"])
    _run([str(VENV_PYTHON), "-m", "pip", "install", "-r", str(req_file)])


def phase2_setup_db(seed: bool):
    import psycopg2

    pg_host = os.environ.get("PGHOST", "localhost")
    pg_port = os.environ.get("PGPORT", "5432")
    pg_user = os.environ.get("PGUSER", "postgres")
    pg_pass = os.environ.get("PGPASSWORD", "ducmanh1801")
    pg_db   = os.environ.get("PGDATABASE", "TOT_AGV")

    print(f"[SETUP] Ket noi PostgreSQL {pg_host}:{pg_port} (user={pg_user}) ...")

    # 1) Tao database neu chua co - phai connect vao DB mac dinh 'postgres' truoc
    conn = psycopg2.connect(host=pg_host, port=pg_port, user=pg_user,
                             password=pg_pass, dbname="postgres")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (pg_db,))
        exists = cur.fetchone()
        if not exists:
            print(f"[SETUP] Database '{pg_db}' chua ton tai -> tao moi")
            cur.execute(f'CREATE DATABASE "{pg_db}"')
        else:
            print(f"[SETUP] Database '{pg_db}' da ton tai")
    conn.close()

    # 2) Chay schema_core.sql tren DB dich
    conn = psycopg2.connect(host=pg_host, port=pg_port, user=pg_user,
                             password=pg_pass, dbname=pg_db)
    conn.autocommit = True
    schema_sql = (DEPLOY_DIR / "schema_core.sql").read_text(encoding="utf-8")
    with conn.cursor() as cur:
        print("[SETUP] Ap dung schema_core.sql (agv_devices, agv_tasks) ...")
        cur.execute(schema_sql)

    if seed:
        seed_sql = (DEPLOY_DIR / "seed_agv_devices.sql").read_text(encoding="utf-8")
        with conn.cursor() as cur:
            print("[SETUP] Nap seed_agv_devices.sql (danh sach AGV da luu) ...")
            cur.execute(seed_sql)
    else:
        print("[SETUP] Bo qua seed (--no-seed) - bang agv_devices se trong")
    conn.close()
    print("[SETUP] Database san sang OK")


def write_local_mode():
    mode_file = ROOT / "mqtt_mode.json"
    mode_file.write_text('{"mode": "local"}', encoding="utf-8")
    print(f"[SETUP] Da ghi {mode_file} -> mode=local")


def main():
    args = sys.argv[1:]
    if "--phase2" in args:
        seed = "--no-seed" not in args
        phase2_setup_db(seed)
        write_local_mode()
        print("\n[SETUP] HOAN TAT OK - chay server bang:")
        print(f'  "{VENV_PYTHON}" "{ROOT / "main.py"}"')
        print("\nDung quen:")
        print("  - Sua MQTT_BROKER trong mqtt_client.py (hoac bien moi truong) "
              "thanh dung IP card mang local cua may nay")
        print("  - Copy deploy/mosquitto.conf.template vao dung vi tri cau hinh "
              "Mosquitto roi khoi dong lai dich vu Mosquitto")
        return

    phase1_create_venv_and_install()

    print("\n[SETUP] Chuyen sang venv vua tao de cai dat database ...")
    reexec_args = [str(VENV_PYTHON), str(Path(__file__).resolve()), "--phase2"]
    if "--no-seed" in args:
        reexec_args.append("--no-seed")
    _run(reexec_args)


if __name__ == "__main__":
    main()
