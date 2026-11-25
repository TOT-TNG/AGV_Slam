"""
run_simulation.py — Chạy TOÀN BỘ mô phỏng: 1 server main.py THẬT (chĩa vào DB +
broker riêng, PORT RIÊNG) + sim_fleet (firmware giả) + sim_task_gen (sinh tác
vụ + tự xác nhận) + sim_monitor (theo dõi & ghi lỗi điều phối) — tách biệt
HOÀN TOÀN khỏi AGV thật (DB riêng, TrafficCoordinator riêng, broker riêng).
Vì server mô phỏng dùng PORT KHÁC (--api-port, mặc định 8001) với server sản
xuất thật (luôn 8000), CẢ HAI CHẠY ĐƯỢC ĐỒNG THỜI trên cùng máy — mô phỏng
KHÔNG cần (và KHÔNG được) dừng server sản xuất.

Chuẩn bị trước khi chạy:
  1. Có 1 Mosquitto (hoặc broker MQTT khác) chạy ở --mqtt-port (mặc định 1884),
     RIÊNG với broker sản xuất (thường 1883) — script này KHÔNG tự khởi
     Mosquitto, chỉ kiểm tra kết nối được tới chưa.
  2. (Tự động) setup_sim_db.py được gọi sẵn bên trong — không cần chạy tay.

Dùng:
  python run_simulation.py --agv-count 15 --duration-hours 2
  (Ctrl+C để dừng sớm — vẫn ghi summary trước khi thoát)
"""
from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SIM_DBNAME = "TOT_AGV_SIM"
SIM_DB_URL = f"postgresql://postgres:ducmanh1801@localhost:5432/{SIM_DBNAME}"
WEB_UI_PORT = 8050   # dùng để in URL xem bản đồ trực tiếp (Web_UI/main.py: app.run(port=8050))

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)   # mqtt_Server/


def _check_broker(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--agv-count", type=int, default=15)
    ap.add_argument("--duration-hours", type=float, default=0.0,
                     help="0 = chạy vô hạn tới khi Ctrl+C")
    ap.add_argument("--mqtt-host", default="localhost")
    ap.add_argument("--mqtt-port", type=int, default=1884)
    ap.add_argument("--api-port", type=int, default=8001,
                     help="Port server mô phỏng lắng nghe — PHẢI khác 8000 (server sản xuất)")
    ap.add_argument("--map-id", default="1788938884681",
                     help="map_id thật cần clone để mô phỏng (xem GET /api/maps/list)")
    ap.add_argument("--agv-type", default="tow", choices=("tow", "trailer", "carry", "mixed"))
    ap.add_argument("--agv-mix", default="",
                     help="Trộn nhiều loại xe, vd 'tow=6,trailer=4,carry=4' (xem setup_sim_db.py); "
                          "có giá trị này thì bỏ qua --agv-count/--agv-type")
    ap.add_argument("--start-nodes", default="",
                     help="Vị trí xuất phát theo loại xe, vd 'tow=221,222;trailer=224' (xem setup_sim_db.py)")
    ap.add_argument("--edge-length", default="",
                     help="Ép độ dài mọi cạnh (m) trong DB mô phỏng, vd '3.5-4'")
    ap.add_argument("--mode", default="natural", choices=("natural", "manual"),
                     help="natural = tự sinh tác vụ ngẫu nhiên như cũ; manual = giao lệnh: xe đứng yên cho tới khi "
                          "người dùng gửi lệnh (bấm icon xe trên bản đồ). Bỏ qua khi dùng --scenario")
    ap.add_argument("--stall-timeout", type=float, default=120.0)
    ap.add_argument("--elevator-backend", default=os.getenv("ELEVATOR_BACKEND", "legacy"),
                     choices=("legacy", "uelev_v2"),
                     help="legacy = thang giả elevator/v1 (open/close); uelev_v2 = thiết bị thang giả nói giao thức "
                          "uelev/v2 của phần cứng + server dùng thư viện elevator_coord (mất mạng trong cabin, plan nối đuôi...)")
    ap.add_argument("--scenario", default=None,
                     help="Đường dẫn file JSON kịch bản test (xem simulation/scenarios/ "
                          "example_same_destination.json) — có giá trị này thì sim_task_gen.py "
                          "chạy đúng kịch bản (biết trước xe nào đi đâu, lúc nào) thay vì sinh "
                          "tác vụ ngẫu nhiên, tự so khớp PASS/FAIL rồi thoát; run_simulation.py "
                          "sẽ tự dừng toàn bộ mô phỏng ngay khi kịch bản xong, không cần Ctrl+C")
    args = ap.parse_args()

    if args.api_port == 8000:
        print("[RUN_SIM] --api-port không được là 8000 (port server sản xuất thật).")
        sys.exit(1)

    if not _check_broker(args.mqtt_host, args.mqtt_port):
        print(f"[RUN_SIM] KHÔNG kết nối được MQTT broker mô phỏng tại "
              f"{args.mqtt_host}:{args.mqtt_port}.")
        print(f"[RUN_SIM] Khởi 1 Mosquitto RIÊNG cho mô phỏng, ví dụ:")
        print(f"[RUN_SIM]   mosquitto -p {args.mqtt_port}")
        print(f"[RUN_SIM] (không dùng port broker sản xuất 1883 để tránh lẫn AGV thật)")
        sys.exit(1)

    ts = time.strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.join(HERE, "logs")
    os.makedirs(log_dir, exist_ok=True)
    server_log_path = os.path.join(log_dir, f"server_stdout_{ts}.log")
    # Chế độ --scenario: cần 1 đường dẫn violations CỐ ĐỊNH biết TRƯỚC, để truyền
    # cho CẢ sim_monitor.py (nơi ghi) và sim_task_gen.py (nơi đọc lại để so khớp
    # expectations) — khác chế độ ngẫu nhiên, nơi sim_monitor.py tự đặt tên theo
    # timestamp của riêng nó và không ai cần đọc lại.
    scenario_violations_path = (
        os.path.join(log_dir, f"violations_scenario_{ts}.jsonl") if args.scenario else None)

    env = os.environ.copy()
    env["DATABASE_URL"] = SIM_DB_URL
    env["PGHOST"] = "localhost"
    env["PGPORT"] = "5432"
    env["PGUSER"] = "postgres"
    env["PGPASSWORD"] = "ducmanh1801"
    env["PGDATABASE"] = SIM_DBNAME
    env["MQTT_BROKER"] = args.mqtt_host
    env["MQTT_PORT"] = str(args.mqtt_port)
    env["MQTT_MODE"] = "local"
    # Bắt buộc local, KHÔNG phụ thuộc mqtt_mode.json thật (file CHUNG với server
    # sản xuất, có thể đang để "cloud") — xem _load_mqtt_mode() trong mqtt_client.py.
    env["MQTT_MODE_OVERRIDE"] = "local"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    # Port RIÊNG cho server mô phỏng (khác 8000 thật) — xem main.py: API_PORT.
    env["API_PORT"] = str(args.api_port)
    env["ELEVATOR_BACKEND"] = args.elevator_backend      # server mô phỏng + sim_fleet dùng CÙNG backend thang

    print(f"[RUN_SIM] setup DB mô phỏng ({args.agv_count} xe, map={args.map_id}, "
          f"loại={args.agv_mix or args.agv_type})...")
    subprocess.run([sys.executable, os.path.join(HERE, "setup_sim_db.py"),
                     "--agv-count", str(args.agv_count),
                     "--map-id", args.map_id,
                     "--agv-type", args.agv_type,
                     "--agv-mix", args.agv_mix,
                     "--start-nodes", args.start_nodes,
                     "--edge-length", args.edge_length], check=True)

    procs: list[subprocess.Popen] = []

    def _stop_all():
        print("[RUN_SIM] đang dừng tất cả tiến trình...")
        for p in procs:
            if p.poll() is None:
                if sys.platform == "win32":
                    # main.py chạy uvicorn reload=True → đẻ thêm tiến trình con
                    # (reloader worker) mà p.terminate() KHÔNG giết theo — để sót
                    # orphan giữ port 8000 sau khi mô phỏng đã "xong". Giết cả
                    # CÂY tiến trình bằng taskkill /T thay vì chỉ 1 PID.
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(p.pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                else:
                    p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()

    scenario_exit_code = None
    try:
        print(f"[RUN_SIM] khởi main.py mô phỏng (log → {server_log_path})...")
        server_log_f = open(server_log_path, "w", encoding="utf-8")
        server_proc = subprocess.Popen(
            [sys.executable, os.path.join(SERVER_DIR, "main.py")],
            cwd=SERVER_DIR, env=env, stdout=server_log_f, stderr=subprocess.STDOUT,
        )
        procs.append(server_proc)
        time.sleep(5)   # chờ FastAPI/uvicorn lên + pool kết nối DB

        print("[RUN_SIM] khởi sim_fleet.py...")
        procs.append(subprocess.Popen(
            [sys.executable, os.path.join(HERE, "sim_fleet.py"),
             "--broker", args.mqtt_host, "--port", str(args.mqtt_port),
             "--db-url", SIM_DB_URL],
            env=env,
        ))

        print("[RUN_SIM] khởi sim_task_gen.py...")
        taskgen_args = [sys.executable, os.path.join(HERE, "sim_task_gen.py"),
                         "--api-base", f"http://localhost:{args.api_port}",
                         "--db-url", SIM_DB_URL]
        if args.scenario:
            taskgen_args += ["--scenario", args.scenario,
                              "--violations-path", scenario_violations_path]
        elif args.duration_hours > 0:
            taskgen_args += ["--duration-hours", str(args.duration_hours)]
        if args.mode == "manual" and not args.scenario:
            taskgen_args += ["--manual"]
            print("[RUN_SIM] CHẾ ĐỘ GIAO LỆNH — không tự sinh tác vụ, xe chạy khi có lệnh gửi từ giao diện.")
        taskgen_proc = subprocess.Popen(taskgen_args)
        procs.append(taskgen_proc)

        print("[RUN_SIM] khởi sim_monitor.py...")
        monitor_args = [sys.executable, os.path.join(HERE, "sim_monitor.py"),
                         "--broker", args.mqtt_host, "--port", str(args.mqtt_port),
                         "--stall-timeout", str(args.stall_timeout),
                         "--server-log", server_log_path,
                         "--api-base", f"http://localhost:{args.api_port}"]
        if scenario_violations_path:
            monitor_args += ["--violations-path", scenario_violations_path]
        elif args.duration_hours > 0:
            monitor_args += ["--duration-hours", str(args.duration_hours)]
        monitor_proc = subprocess.Popen(monitor_args)
        procs.append(monitor_proc)

        # Xem TRỰC TIẾP trên bản đồ (độc lập với cách khởi mô phỏng — CLI hay Web
        # UI "Mô phỏng Fleet" đều ra CÙNG 1 server mô phỏng, chỉ là trang XEM gọi
        # thẳng REST API của nó, không quan tâm ai đã khởi): mở URL này trên máy
        # đang chạy Web_UI (mặc định port 8050) — đổi "localhost" thành IP máy đó
        # nếu xem từ máy khác.
        _monitor_url = (f"http://localhost:{WEB_UI_PORT}/assets/task_execute.html"
                         f"?view=monitor&api_port={args.api_port}&map_id={args.map_id}")
        print(f"[RUN_SIM] Xem trực tiếp trên bản đồ: {_monitor_url}")

        if args.scenario:
            print(f"[RUN_SIM] đang chạy kịch bản '{args.scenario}' — log tại {log_dir}. "
                  f"Tự dừng ngay khi kịch bản xong (hoặc Ctrl+C để dừng sớm).")
            # Chờ ĐÚNG sim_task_gen.py (nơi chạy kịch bản) thoát, KHÔNG chờ
            # monitor — monitor chạy vô thời hạn (duration_hours=0 ở chế độ
            # scenario) nên sẽ không bao giờ tự thoát.
            scenario_exit_code = taskgen_proc.wait()
        else:
            print(f"[RUN_SIM] đang chạy — log tại {log_dir}. Ctrl+C để dừng sớm.")
            # Chờ sim_monitor tự kết thúc (hết --duration-hours) hoặc Ctrl+C.
            monitor_proc.wait()
            scenario_exit_code = None
    except KeyboardInterrupt:
        print("[RUN_SIM] nhận Ctrl+C...")
        scenario_exit_code = None
    finally:
        _stop_all()
        if args.scenario:
            print(f"[RUN_SIM] XONG kịch bản — xem {log_dir}/scenario_result_*.json")
        else:
            print(f"[RUN_SIM] XONG. Xem {log_dir}/violations_*.jsonl và summary_*.json")

    if scenario_exit_code is not None:
        sys.exit(scenario_exit_code)


if __name__ == "__main__":
    main()
