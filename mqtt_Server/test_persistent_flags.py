"""Test persistent_flags: tập cờ ghi xuyên DB đúng thứ tự, khôi phục không ghi ngược, theo dõi lấy hàng theo lượt được lưu.
Chạy: PYTHONIOENCODING=utf-8 python test_persistent_flags.py   (pool asyncpg giả ghi lại câu SQL)."""
import asyncio

import persistent_flags as PF
import task_queue as TQ

_pass = _fail = 0


def check(cond, msg):
    global _pass, _fail
    if cond:
        _pass += 1
        print("  PASS:", msg)
    else:
        _fail += 1
        print("  FAIL:", msg)


class FakeConn:
    def __init__(self, log):
        self.log = log

    async def execute(self, sql, *args):
        await asyncio.sleep(0)               # nhường vòng lặp: kiểm tra việc ghi TUẦN TỰ
        self.log.append((" ".join(sql.split())[:40], args))

    def transaction(self):
        class _T:
            async def __aenter__(s): return s
            async def __aexit__(s, *a): return False
        return _T()


class FakePool:
    def __init__(self):
        self.log = []

    def acquire(self):
        pool = self

        class _A:
            async def __aenter__(s): return FakeConn(pool.log)
            async def __aexit__(s, *a): return False
        return _A()


async def main():
    pool = FakePool()
    PF.flag_store.set_pool(pool)

    print("[test] PersistentPairSet: add/discard ghi đúng thứ tự (add → discard cùng khoá không bị đảo)")
    s = PF.PersistentPairSet("empty_pickup")
    s.add(("AGV1", "4"))
    s.add(("AGV1", "4"))                      # trùng → không ghi lại
    s.discard(("AGV1", "4"))
    s.discard(("AGV1", "4"))                  # không còn → không ghi
    s.add(("AGV2", "9"))
    await asyncio.sleep(0.2)
    kinds = [(q.split()[0], a) for q, a in pool.log]
    check(kinds == [("INSERT", ("empty_pickup", "AGV1", "4")), ("DELETE", ("empty_pickup", "AGV1", "4")),
                    ("INSERT", ("empty_pickup", "AGV2", "9"))], f"đúng 3 câu theo thứ tự: {kinds}")
    check(s == {("AGV2", "9")} and ("AGV2", "9") in s, "hành vi set bình thường")

    print("[test] load() nạp từ DB không ghi ngược")
    pool.log.clear()
    s2 = PF.PersistentPairSet("confirm_only")
    s2.load([("A", "1"), ("B", "2")])
    await asyncio.sleep(0.1)
    check(len(s2) == 2 and ("A", "1") in s2 and not pool.log, "nạp 2 phần tử, không có câu SQL nào")

    print("[test] clear/pop/update")
    s2.pop()
    s2.update([("C", "3"), ("C", "3")])
    s2.clear()
    await asyncio.sleep(0.2)
    ops = [q.split()[0] for q, _a in pool.log]
    check(ops == ["DELETE", "INSERT", "DELETE"] and len(s2) == 0, f"pop→DELETE, update→INSERT(1), clear→DELETE kind: {ops}")

    print("[test] theo dõi lấy hàng theo lượt được lưu và dọn khi hết lượt")
    pool.log.clear()
    q = TQ.AGVTaskQueue()
    q.mark_session_pickup("sess1", "64")
    q.mark_session_pickup("sess1", "64")      # trùng
    q.mark_session_pickup("sess1", "19")
    await asyncio.sleep(0.2)
    ins = [a for sql, a in pool.log if sql.startswith("INSERT")]
    check(ins == [("session_pickup", "sess1", "64"), ("session_pickup", "sess1", "19")], f"ghi 2 node: {ins}")
    pool.log.clear()
    q._clear_session_pickups("sess1")
    await asyncio.sleep(0.1)
    check(len(pool.log) == 1 and pool.log[0][0].startswith("DELETE") and pool.log[0][1] == ("session_pickup", "sess1"), "hết lượt → xoá cả nhóm")
    q2 = TQ.AGVTaskQueue()
    q2.restore_session_pickups([("sessX", "64"), ("sessX", "19")])
    check(q2.session_has_pickup("sessX", "64") and q2.session_has_pickup("sessX", "19") and not q2.session_has_pickup("sessX", "7"),
          "khôi phục theo dõi lấy hàng sau khi khởi động lại")

    print("[test] replace(): mỗi (kind, grp) chỉ giữ 1 giá trị")
    pool.log.clear()
    PF.flag_store.replace("ride_ctx", "AGV1", '{"a":1}')
    await asyncio.sleep(0.1)
    check([q_.split()[0] for q_, _a in pool.log] == ["DELETE", "INSERT"], "xoá cũ rồi ghi mới")

    print("[test] không có pool → vẫn chạy trong RAM, không lỗi")
    PF.flag_store._pool = None
    s3 = PF.PersistentPairSet("x")
    s3.add(("A", "1")); s3.discard(("A", "1"))
    check(len(s3) == 0, "không lỗi khi chưa gắn DB")


asyncio.run(main())
print()
print(f"KẾT QUẢ: {_pass} pass, {_fail} fail")
raise SystemExit(1 if _fail else 0)
