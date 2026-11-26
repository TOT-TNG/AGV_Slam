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
print("[test] _trailer_has_exit_script: quyết định có lùi dọc đường cũ hay dùng kịch bản lùi mù + quay")
check(M._trailer_has_exit_script("T1", "10", cfg), "rơ-moóc + trạm có kịch bản → True (không lùi thẳng dọc đường cũ)")
check(not M._trailer_has_exit_script("K1", "10", cfg), "xe kéo → False")
check(not M._trailer_has_exit_script("C1", "10", cfg), "xe chở → False")
check(not M._trailer_has_exit_script("T1", "10", {"locationType": "NORMAL", "exit_reverse_ms": 3000, "exit_turn": "left"}), "node thường (không phải trạm) → False")
check(not M._trailer_has_exit_script("T1", "10", {"locationType": "CHARGER"}), "trạm chưa khai kịch bản và không phải ngõ cụt → False")
check(M._trailer_has_exit_script("T1", "10", {"arrival_action": "wait_charge", "exit_reverse_ms": 2000, "exit_turn": "right"}), "trạm nhận diện theo wait_charge → True")

print(f"KẾT QUẢ: {_p} pass, {_f} fail")
raise SystemExit(1 if _f else 0)
