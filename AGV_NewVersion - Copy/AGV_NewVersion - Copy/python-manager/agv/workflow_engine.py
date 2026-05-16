"""
WorkflowEngine — Thực thi hành động đặc biệt khi AGV đến từng node.

Cách hoạt động:
  1. Mỗi khi AGV chuyển đến tag mới, gọi trigger(agv, tag_id, mqtt_client).
  2. Engine tìm rule phù hợp (tag_id + mission_type).
  3. Thực thi tuần tự các step trong rule (chạy nền, không block main thread).
  4. Nếu rule có step BLOCKING (wait_time, wait_relay...) → đặt cờ is_blocking.
  5. run_hmi_handler kiểm tra is_blocking() trước khi gửi lệnh di chuyển tiếp.

Cấu trúc config/tag_actions.json:
  {
    "rules": [
      {
        "id":           "horn_before_intersection",
        "tag_id":       61,
        "mission_type": "any",           // "any" khớp tất cả, hoặc "delivery"|"pickup"|...
        "description":  "Bấm còi trước ngã tư 61",
        "blocking":     false,           // false = chạy nền, không chặn AGV đi
        "steps": [
          {"type": "agv_command", "cmd": "horn"},
          {"type": "wait_time",   "ms": 500}
        ]
      }
    ]
  }

Step types hỗ trợ:
  mqtt_publish   — Gửi bản tin MQTT đến topic bất kỳ (PLC, relay, thiết bị khác)
  wait_time      — Dừng chờ N milliseconds trước khi bước tiếp theo
  agv_command    — Gửi lệnh tức thì đến AGV (horn, stop, run, blink_on, blink_off...)
  set_speed      — Thay đổi tốc độ AGV tại thẻ hiện tại
  log_message    — Ghi log ra console (debug/audit)
"""

import json
import os
import time
import threading
import uuid


# ─── WorkflowEngine ───────────────────────────────────────────────────────────
class WorkflowEngine:

    def __init__(self, config_file: str = "config/tag_actions.json"):
        self.config_file  = config_file
        self._rules: list = []
        # Index: (tag_id, mission_type) → list[rule]  (cùng tag có thể có nhiều rule)
        self._index: dict = {}
        # Trạng thái chạy: agv_id → threading.Event (set = done, not-set = blocking)
        self._block_events: dict = {}
        # Thread đang chạy: agv_id → Thread
        self._threads: dict = {}
        self._load()

    # ── Load / Save ───────────────────────────────────────────────────────────
    def _load(self):
        if not os.path.exists(self.config_file):
            print(f"[WF] Không tìm thấy {self.config_file}. Workflow chạy không có rule.")
            return
        try:
            with open(self.config_file, encoding="utf-8") as f:
                data = json.load(f)
            self._rules = data.get("rules", [])
            self._rebuild_index()
            print(f"[WF] Loaded {len(self._rules)} rule(s) từ {self.config_file}")
        except Exception as e:
            print(f"[WF] Lỗi load config: {e}")

    def _rebuild_index(self):
        self._index.clear()
        for rule in self._rules:
            tag = int(rule.get("tag_id", 0))
            mt  = rule.get("mission_type", "any")
            key = (tag, mt)
            if key not in self._index:
                self._index[key] = []
            self._index[key].append(rule)

    def reload(self):
        """Tải lại config từ file (dùng sau khi lưu UI)."""
        self._load()

    def save(self):
        """Lưu rules hiện tại ra file JSON."""
        try:
            os.makedirs(os.path.dirname(self.config_file) or ".", exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump({"rules": self._rules}, f, indent=4, ensure_ascii=False)
            print(f"[WF] Saved {len(self._rules)} rule(s) → {self.config_file}")
        except Exception as e:
            print(f"[WF] Lỗi save: {e}")

    # ── Trigger ───────────────────────────────────────────────────────────────
    def trigger(self, agv, tag_id: int, mqtt_client) -> bool:
        """
        Kích hoạt workflow cho AGV tại tag_id (nếu có rule phù hợp).
        Gọi mỗi khi current_tag thay đổi.
        Returns True nếu có ít nhất 1 rule được kích hoạt.
        """
        rules = self._find_rules(tag_id, agv.current_task_type)
        if not rules:
            return False

        triggered = False
        for rule in rules:
            steps    = rule.get("steps", [])
            blocking = rule.get("blocking", False)
            if not steps:
                continue

            # Bỏ qua nếu đang có workflow blocking chưa xong cho AGV này
            if blocking and not self._is_done(agv.id):
                print(f"[WF] {agv.id}: Workflow blocking chưa xong, bỏ qua rule '{rule.get('id')}'")
                continue

            self._run_async(agv, rule, steps, blocking, mqtt_client)
            triggered = True

        return triggered

    def _find_rules(self, tag_id: int, mission_type: str) -> list:
        """Trả về tất cả rules phù hợp với (tag_id, mission_type) hoặc (tag_id, 'any')."""
        results = []
        results.extend(self._index.get((tag_id, mission_type), []))
        if mission_type != "any":
            results.extend(self._index.get((tag_id, "any"), []))
        return results

    # ── Blocking check ────────────────────────────────────────────────────────
    def is_blocking(self, agv_id: str) -> bool:
        """True nếu đang có workflow BLOCKING chạy cho AGV này."""
        return not self._is_done(agv_id)

    def _is_done(self, agv_id: str) -> bool:
        evt = self._block_events.get(agv_id)
        return evt is None or evt.is_set()

    # ── Execution ─────────────────────────────────────────────────────────────
    def _run_async(self, agv, rule, steps, blocking, mqtt_client):
        rule_id = rule.get("id", "?")

        if blocking:
            evt = threading.Event()
            self._block_events[agv.id] = evt
        else:
            evt = None

        def _worker():
            print(f"[WF] ▶ {agv.id} @ tag {agv.current_tag} → rule '{rule_id}' ({len(steps)} steps)")
            for step in steps:
                self._exec_step(agv, step, mqtt_client)
            if evt is not None:
                evt.set()
                print(f"[WF] ✓ {agv.id} rule '{rule_id}' xong — unblocked")

        t = threading.Thread(target=_worker, name=f"wf_{agv.id}_{rule_id}", daemon=True)
        self._threads[agv.id] = t
        t.start()

    def _exec_step(self, agv, step: dict, mqtt_client):
        stype = step.get("type", "")
        try:
            # ── mqtt_publish ──────────────────────────────────────────────────
            if stype == "mqtt_publish":
                topic   = step.get("topic", "")
                payload = str(step.get("payload", ""))
                if topic and mqtt_client:
                    mqtt_client.publish(topic, payload)
                    print(f"[WF]   mqtt_publish → {topic}: {payload}")

            # ── wait_time ─────────────────────────────────────────────────────
            elif stype == "wait_time":
                ms = int(step.get("ms", 0))
                if ms > 0:
                    print(f"[WF]   wait_time {ms} ms")
                    time.sleep(ms / 1000.0)

            # ── agv_command ───────────────────────────────────────────────────
            elif stype == "agv_command":
                cmd = step.get("cmd", "")
                if cmd:
                    agv.send_command(cmd)
                    print(f"[WF]   agv_command → {agv.id}: {cmd}")

            # ── set_speed ─────────────────────────────────────────────────────
            elif stype == "set_speed":
                speed = int(step.get("speed", 60))
                if mqtt_client:
                    cmd_id  = str(uuid.uuid4())[:8]
                    payload = json.dumps({
                        "c": "plan",
                        "d": [{"t": int(agv.current_tag), "a": 4, "v": speed}],
                        "id": cmd_id,
                    })
                    mqtt_client.publish(agv.topic_order, payload)
                    print(f"[WF]   set_speed → {agv.id}: {speed}")

            # ── log_message ───────────────────────────────────────────────────
            elif stype == "log_message":
                msg = step.get("message", "")
                print(f"[WF LOG] {agv.id}@tag{agv.current_tag} [{agv.current_task_type}]: {msg}")

            else:
                print(f"[WF] Unknown step type: '{stype}'")

        except Exception as e:
            print(f"[WF] Lỗi step {step}: {e}")

    # ── CRUD (dùng từ UI) ─────────────────────────────────────────────────────
    def add_or_update_rule(self, rule: dict):
        """Thêm hoặc cập nhật rule (theo id). Rebuild index."""
        self._rules = [r for r in self._rules if r.get("id") != rule.get("id")]
        self._rules.append(rule)
        self._rebuild_index()

    def delete_rule(self, rule_id: str):
        self._rules = [r for r in self._rules if r.get("id") != rule_id]
        self._rebuild_index()

    def get_rules(self) -> list:
        return list(self._rules)
