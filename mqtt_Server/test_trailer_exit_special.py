"""Test: bước 'lùi mù + quay đầu' khi rơ-moóc rời trạm dùng chung cho go_to và lệnh khu chờ/về trạm.
Chạy: PYTHONIOENCODING=utf-8 python test_trailer_exit_special.py"""
import main as M
from line_agv_plan_builder import ACTION_REVERSE_BLIND, ACTION_TURN_L, ACTION_TURN_R

_p = _f = 0
def check(c, m):
    global _p, _f
    if c: _p += 1; print("  PASS:", m)
    else: _f += 1; print("  FAIL:", m)

types = {"T1": "trailer", "K1": "tow", "C1": "carry"}
import agv_registry as _ar
_ar.agv_registry.get_config = lambda a: {"agv_type": types.get(a, "")}
path = ["10", "9", "8"]
cfg = {"locationType": "CHARGER", "exit_reverse_ms": 3000, "exit_turn": "left"}

st = M._build_trailer_exit_steps("T1", path, True, cfg, {"10_9": 70})
check([s["a"] for s in st][1:3] == [ACTION_REVERSE_BLIND, ACTION_TURN_L] and st[1]["v"] == 3000, f"rơ-moóc ở trạm → lùi mù 3000ms rồi quay trái ({len(st)} bước)")
check(all(isinstance(s["t"], int) for s in st), "'t' là số nguyên")
check(st[-1]["v"] == 70, "tốc độ lấy theo cạnh path[0]->path[1]")
st = M._build_trailer_exit_steps("T1", path, True, dict(cfg, exit_turn="right"), {})
check(st[2]["a"] == ACTION_TURN_R, "quay phải theo cấu hình")
check(M._build_trailer_exit_steps("K1", path, True, cfg, {}) == [], "xe kéo (tow) → không chèn")
check(M._build_trailer_exit_steps("C1", path, True, cfg, {}) == [], "xe chở (carry) → không chèn")
check(M._build_trailer_exit_steps("T1", path, False, cfg, {}) == [], "xe không ở trạm → không chèn")
check(M._build_trailer_exit_steps("T1", path, True, {"locationType": "CHARGER"}, {}) == [], "trạm chưa khai exit_reverse_ms/exit_turn → không chèn")
print(f"KẾT QUẢ: {_p} pass, {_f} fail")
raise SystemExit(1 if _f else 0)
