"""Test kênh run/stop có cmd_ack (09-ack-lenh-fms.md §2.2). Chạy: python test_agv_cmd_channel.py"""
import os
os.environ["AGV_CMD_ACK_MODE"] = "auto"
import agv_cmd_channel as M

_pass = _fail = 0


def check(cond, msg):
    global _pass, _fail
    if cond:
        _pass += 1
        print("  PASS:", msg)
    else:
        _fail += 1
        print("  FAIL:", msg)


def make():
    t = {"now": 100.0}
    sent, avail, expired = [], {"v": True}, []
    ch = M.AgvCommandChannel()
    ch.configure(publish=lambda a, p: (sent.append((a, p)), True)[1],
                 is_available=lambda a: avail["v"],
                 on_expired=lambda a, c: expired.append((a, c)),
                 clock=lambda: t["now"])
    return ch, t, sent, avail, expired


print("[test] gửi + ACK khớp id → dừng gửi lặp")
ch, t, sent, avail, exp = make()
ch.send("A", "run")
check(len(sent) == 1 and sent[0][1]["c"] == "run" and len(sent[0][1]["id"]) == 8, "gửi 1 lần, id 8 ký tự")
rid = sent[0][1]["id"]
t["now"] += 1; ch.on_state("A", {}, False, False)
check(len(sent) == 1, "<3s chưa thấy ACK: chưa gửi lại")
ch.on_state("A", {"cmd_ack": rid}, False, False)
t["now"] += 10; ch.on_state("A", {"cmd_ack": rid}, False, False)
check(len(sent) == 1 and ch.pending("A") is None, "ACK khớp → xoá chờ, không gửi thêm")

print("[test] không ACK → gửi lại CÙNG id mỗi 3s, tối đa 4 lần rồi bỏ")
ch, t, sent, avail, exp = make()
ch.send("A", "stop"); ids = set()
for _ in range(12):
    t["now"] += 3.1
    ch.on_state("A", {"cmd_ack": "old"}, False, False)   # xe firmware mới nhưng chưa nhận lệnh này
ids = {p["id"] for _, p in sent}
check(len(sent) == M.MAX_SENDS and len(ids) == 1, f"đúng {M.MAX_SENDS} lần gửi cùng 1 id")
check(ch.pending("A") is None and exp == [("A", "stop")], "hết lượt → bỏ + báo expired")

print("[test] xe offline: giữ lệnh, KHÔNG đốt lượt gửi; online lại gửi bù")
ch, t, sent, avail, exp = make()
avail["v"] = False
ch.send("A", "run")
for _ in range(30):
    t["now"] += 5; ch.tick()
check(sent == [] and ch.pending("A") == "run", "offline 150s: không gửi, vẫn giữ lệnh")
avail["v"] = True
ch.on_state("A", {"cmd_ack": "x"}, False, False)
check(len(sent) == 1, "online lại → gửi bù ngay")
check(sent[0][1]["id"] and ch.stats["expired"] == 0, "chưa bị tính hết lượt")
ch.on_state("A", {"cmd_ack": sent[0][1]["id"]}, False, False)
check(ch.pending("A") is None, "ACK sau khi gửi bù → xong")

print("[test] lệnh sau đè lệnh trước (run rồi stop → chỉ còn stop)")
ch, t, sent, avail, exp = make()
avail["v"] = False
ch.send("A", "run"); ch.send("A", "stop")
avail["v"] = True; ch.tick()
check([p["c"] for _, p in sent] == ["stop"], "chỉ gửi stop")

print("[test] firmware cũ (chưa từng báo cmd_ack): dựa vào state")
ch, t, sent, avail, exp = make()
ch.send("B", "stop")
t["now"] += 1; ch.on_state("B", {}, False, True)
check(ch.pending("B") == "stop", "stop: xe còn driving → chưa xong")
t["now"] += 1; ch.on_state("B", {}, False, False)
check(ch.pending("B") is None, "stop: driving=False ∧ paused=False → xong")
ch.send("B", "run"); t["now"] += 1; ch.on_state("B", {}, True, False)
check(ch.pending("B") == "run", "run: paused=true → chưa xong")
ch.on_state("B", {}, False, False)
check(ch.pending("B") is None, "run: paused=false → xong")

print("[test] id cũ của lệnh trước không làm xong lệnh mới")
ch, t, sent, avail, exp = make()
ch.send("A", "run"); first = sent[0][1]["id"]; ch.on_state("A", {"cmd_ack": first}, False, False)
ch.send("A", "stop")
ch.on_state("A", {"cmd_ack": first}, False, False)
check(ch.pending("A") == "stop", "cmd_ack cũ ≠ id mới → vẫn chờ")

print("[test] on_acked: gọi khi xe xác nhận (cmd_ack khớp hoặc firmware cũ theo state)")
ch, t, sent, avail, exp = make()
acked = []
ch.configure(publish=lambda a, p: (sent.append((a, p)), True)[1], is_available=lambda a: True,
             on_expired=lambda a, c: exp.append((a, c)), on_acked=lambda a, c: acked.append((a, c)),
             clock=lambda: t["now"])
ch.send("A", "run"); rid = sent[0][1]["id"]
ch.on_state("A", {"cmd_ack": "khac"}, False, False)
check(acked == [], "cmd_ack khác id → chưa gọi on_acked")
ch.on_state("A", {"cmd_ack": rid}, False, False)
check(acked == [("A", "run")], "cmd_ack khớp → on_acked(A, run) đúng 1 lần")
ch.on_state("A", {"cmd_ack": rid}, False, False)
check(acked == [("A", "run")], "state lặp lại không gọi thêm")
ch.send("B", "stop"); t["now"] += 1; ch.on_state("B", {}, False, False)
check(acked[-1] == ("B", "stop"), "firmware cũ: xong theo state → on_acked")

print("[test] chế độ off: gửi thẳng, không id")
os.environ["AGV_CMD_ACK_MODE"] = "off"
ch, t, sent, avail, exp = make()
ch.send("A", "run")
check(sent == [("A", {"c": "run"})] and ch.pending("A") is None, "off → {'c':'run'} một lần")
os.environ["AGV_CMD_ACK_MODE"] = "auto"

print(f"\nKẾT QUẢ: {_pass} pass, {_fail} fail")
raise SystemExit(1 if _fail else 0)
