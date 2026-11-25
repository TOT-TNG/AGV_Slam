"""Test nhận diện thang đã kết nối (elevator_registry). Chạy: python test_elevator_registry.py"""
import time

import elevator_registry as er

R = er.ElevatorRegistry
fails = []


def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


r = R()
check("chưa thấy → never", r.info("E1")["link"] == "never")

r.on_state("VietDuc", "E1", "closed", 1, retained=True)
i = r.info("E1")
check("chỉ có tin retained → stale, KHÔNG online", i["link"] == "stale" and not i["online"])

r.on_state("VietDuc", "E1", "open", 1, retained=False)
check("có tin state sống → online (nguồn state)", r.info("E1")["online"] and r.info("E1")["source"] == "state")

er.LIVE_TIMEOUT_SEC = 0.2
time.sleep(0.3)
check("im quá hạn → offline", r.info("E1")["link"] == "offline")
er.LIVE_TIMEOUT_SEC = 30.0

r.on_connection("VietDuc", "E2", b'{"connectionState":"ONLINE"}')
check("connection ONLINE (JSON) → online", r.info("E2")["online"] and r.info("E2")["source"] == "connection")
r.on_connection("VietDuc", "E2", b"OFFLINE")
check("connection OFFLINE (chuỗi thô, LWT) → offline", r.info("E2")["link"] == "offline")
r.on_state("VietDuc", "E2", "closed", 2, retained=False)
check("OFFLINE nhưng tin state sống mới hơn → online", r.info("E2")["online"])

r.on_connection("VietDuc", "E3", b"???")
check("connection rác bị bỏ qua", r.info("E3")["link"] == "never")
r.on_connection("VietDuc", "E3", b"ONLINE")
r.on_state("VietDuc", "E3", "closed", 1, retained=True)
check("ONLINE qua connection + state retained → vẫn online", r.info("E3")["online"])
check("seen_ids đủ", set(r.seen_ids()) == {"E1", "E2", "E3"})

print("\nTỔNG:", "TẤT CẢ ĐẠT" if not fails else f"{len(fails)} LỖI: {fails}")
raise SystemExit(1 if fails else 0)
