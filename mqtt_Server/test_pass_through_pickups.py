"""Test: lượt go_charge/go_wait (và chặng trung gian của chuỗi đi thang tới chúng) chỉ ĐI QUA node lấy/thả hàng.
Chạy: PYTHONIOENCODING=utf-8 python test_pass_through_pickups.py"""
from collections import deque
from task_queue import AGVTaskQueue, QueuedCommand

_p = _f = 0
def check(c, m):
    global _p, _f
    if c: _p += 1; print("  PASS:", m)
    else: _f += 1; print("  FAIL:", m)

def cmd(command, leg=False, dest=None):
    return QueuedCommand(cmd_id=command + str(id(dest)), agv_id="A", command=command, dest_node=dest, chain_leg=leg)

def mk(running, queued):
    q = AGVTaskQueue()
    q._running["A"] = running
    q._queues["A"] = deque(queued)
    return q

check(mk(cmd("go_wait"), []).heading_to_special("A"), "đang chạy go_wait → đi qua")
check(mk(cmd("go_charge"), []).heading_to_special("A"), "đang chạy go_charge → đi qua")
check(not mk(cmd("go_to", dest="9"), [cmd("go_charge")]).heading_to_special("A"), "giao hàng thường rồi mới về sạc → vẫn xử lý lấy/thả")
check(mk(cmd("go_to", leg=True, dest="6"), [cmd("elev_book"), cmd("elev_ride"), cmd("go_to", leg=True), cmd("go_wait")]).heading_to_special("A"),
      "chặng trung gian của chuỗi đi thang tới điểm chờ → đi qua")
check(not mk(cmd("go_to", leg=True, dest="6"), [cmd("elev_ride"), cmd("go_to", dest="9"), cmd("go_charge")]).heading_to_special("A"),
      "chuỗi giao hàng (đích thật là go_to) rồi mới go_charge → không đi qua")
check(not mk(None, []).heading_to_special("A"), "không có lệnh chạy → False")
print(f"KẾT QUẢ: {_p} pass, {_f} fail")
raise SystemExit(1 if _f else 0)
