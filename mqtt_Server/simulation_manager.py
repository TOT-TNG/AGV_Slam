"""
simulation_manager.py — Quản lý phiên chạy mô phỏng (Test Run).
AGV tự động chạy tuần hoàn theo lộ trình định sẵn, không cần người xác nhận.
"""
import asyncio
import uuid
import time
from dataclasses import dataclass, field
from typing import Optional


# ═══════════════════════════════════════════════════════════════
# SimSession — 1 phiên chạy mô phỏng
# ═══════════════════════════════════════════════════════════════

@dataclass
class SimSession:
    session_id:   str
    agv_id:       str
    route:        list[str]   # danh sách node_id gốc
    route_type:   str         # loop | pingpong
    total_cycles: int
    delay_s:      float       # giây chờ tại mỗi điểm trước khi đi tiếp

    # Trạng thái
    current_cycle: int = 0
    current_step:  int = 0    # index trong full_sequence
    status: str = "idle"      # idle|running|paused|completed|stopped|error
    error_msg: str = ""

    # Stats
    started_at:     float = field(default_factory=time.time)
    cycle_times:    list  = field(default_factory=list)
    _cycle_start:   float = field(default_factory=time.time)
    dispatch_count: int   = 0
    error_count:    int   = 0

    # Internal task handle
    _task: Optional[asyncio.Task] = field(default=None, repr=False)

    # Pingpong direction tracking (1=fwd, -1=bwd)
    _direction: int = 1
    # Current pass sequence (for status display)
    _current_pass_seq: list = field(default_factory=list)

    @property
    def full_sequence(self) -> list[str]:
        """Sequence đầy đủ 1 cycle."""
        if len(self.route) < 2:
            return self.route
        if self.route_type == "pingpong":
            # A→B→C→B→A: forward rồi backward (không lặp endpoints)
            # Dùng reversed(route)[1:] thay vì route[-2:0:-1] vì formula cũ bị
            # lỗi với route 2 phần tử (trả về []).
            return self.route + list(reversed(self.route))[1:]
        # loop: A→B→C→...→Z (rồi quay lại A ở cycle mới)
        return self.route

    @property
    def current_dest(self) -> Optional[str]:
        seq = self.full_sequence
        if not seq:
            return None
        return seq[self.current_step % len(seq)]

    def advance_step(self) -> None:
        seq = self.full_sequence
        if not seq:
            return
        self.current_step += 1
        if self.current_step >= len(seq):
            self.current_step = 0
            self.current_cycle += 1
            elapsed = time.time() - self._cycle_start
            self.cycle_times.append(round(elapsed, 2))
            self._cycle_start = time.time()

    @property
    def progress_pct(self) -> float:
        if self.total_cycles == 0:
            return 100.0
        seq_len = max(len(self.full_sequence), 1)
        done = self.current_cycle + self.current_step / seq_len
        return min(100.0, round(done / self.total_cycles * 100, 1))

    @property
    def eta_s(self) -> Optional[int]:
        if not self.cycle_times:
            return None
        avg = sum(self.cycle_times) / len(self.cycle_times)
        remaining = self.total_cycles - self.current_cycle
        return max(0, round(avg * remaining))

    def to_dict(self) -> dict:
        seq = self.full_sequence
        return {
            "session_id":    self.session_id,
            "agv_id":        self.agv_id,
            "route":         self.route,
            "route_type":    self.route_type,
            "total_cycles":  self.total_cycles,
            "delay_s":       self.delay_s,
            "current_cycle": self.current_cycle,
            "current_step":  self.current_step,
            "current_dest":  self.current_dest,
            "sequence_len":  len(seq),
            "status":        self.status,
            "error_msg":     self.error_msg,
            "progress_pct":  self.progress_pct,
            "eta_s":         self.eta_s,
            "dispatch_count":self.dispatch_count,
            "error_count":   self.error_count,
            "elapsed_s":     round(time.time() - self.started_at),
            "avg_cycle_s":   round(sum(self.cycle_times)/len(self.cycle_times), 1)
                             if self.cycle_times else None,
        }


# ═══════════════════════════════════════════════════════════════
# Simulation dispatch helper
# ═══════════════════════════════════════════════════════════════

def _sim_dispatch(agv_task_queue, agv_id, command, dest_node, session_id, session_label):
    """
    Dispatch lệnh cho simulation — chạy trong thread pool.
    approach_dir='bwd' đã được override trong _dispatch_go_to của main.py
    (cho toàn bộ path, không chỉ dest node).
    """
    return agv_task_queue.dispatch_or_queue(
        agv_id, command, dest_node, None, session_id, session_label
    )


# ═══════════════════════════════════════════════════════════════
# Registry
# ═══════════════════════════════════════════════════════════════

_sessions:     dict[str, SimSession] = {}   # {session_id: session}
_agv_sessions: dict[str, str]        = {}   # {agv_id: session_id}

# Tập AGV đang trong chế độ mô phỏng → dùng để force direction=fwd
# khi build plan (bỏ qua approach_dir='bwd' ở node đích)
_sim_active_agvs: set[str] = set()


def get_session(session_id: str) -> Optional[SimSession]:
    return _sessions.get(session_id)


def get_session_by_agv(agv_id: str) -> Optional[SimSession]:
    sid = _agv_sessions.get(agv_id)
    return _sessions.get(sid) if sid else None


def list_sessions() -> list[dict]:
    return [s.to_dict() for s in _sessions.values()]


def _stop_existing(agv_id: str) -> None:
    """Dừng phiên cũ nếu AGV đang có phiên active."""
    old = get_session_by_agv(agv_id)
    if old:
        old.status = "stopped"
        if old._task and not old._task.done():
            old._task.cancel()
        _agv_sessions.pop(agv_id, None)


def create_session(
    agv_id:       str,
    route:        list[str],
    route_type:   str   = "loop",
    total_cycles: int   = 10,
    delay_s:      float = 1.0,
) -> SimSession:
    _stop_existing(agv_id)
    sid  = uuid.uuid4().hex[:10]
    sess = SimSession(
        session_id=sid, agv_id=agv_id, route=route,
        route_type=route_type, total_cycles=total_cycles, delay_s=delay_s,
    )
    _sessions[sid] = sess
    _agv_sessions[agv_id] = sid
    return sess


def remove_session(session_id: str) -> None:
    sess = _sessions.pop(session_id, None)
    if sess:
        _agv_sessions.pop(sess.agv_id, None)


# ═══════════════════════════════════════════════════════════════
# Main simulation loop
# ═══════════════════════════════════════════════════════════════

async def run_session(sess: SimSession) -> None:
    """
    Dispatch FULL PASS (toàn bộ chiều đi) thay vì từng node một.
    Giống hệt real commands: plan builder tự tính turn/speed đúng theo bản đồ.
    Auto-confirm TẤT CẢ lifecycle stops (intermediate + final) trong pass.
    """
    from task_queue import agv_task_queue, CMD_GO_TO
    from line_agv_handler import line_agv_handler

    print(f"[SIM] {sess.agv_id}: start session={sess.session_id} "
          f"type={sess.route_type} cycles={sess.total_cycles} route={sess.route}")

    sess.status       = "running"
    sess._cycle_start = time.time()
    _sim_active_agvs.add(sess.agv_id)

    # Reset trạng thái
    try:
        _st = line_agv_handler.state_store.get(sess.agv_id)
        if _st:
            _st.last_transit_direction = ''
            _st.task_lifecycle = None
            print(f"[SIM] {sess.agv_id}: state reset (dir=fwd, lifecycle=None)")
    except Exception as _e:
        print(f"[SIM] state reset error: {_e}")

    # ── Auto-confirm helper ────────────────────────────────────────────────
    async def _wait_and_confirm(dest: str) -> bool:
        """
        Chờ AGV đến dest, auto-confirm lifecycle stops dọc đường.
        Sau khi confirm tại ĐÍCH THỰC SỰ, thêm delay nhỏ để
        task_queue settle trước khi simulation dispatch bước tiếp.
        """
        wait_start = time.time()
        while True:
            await asyncio.sleep(0.5)
            if sess.status == "stopped":
                return False
            while sess.status == "paused":
                await asyncio.sleep(0.5)
            if time.time() - wait_start > 600:
                sess.error_count += 1
                return False
            _st = line_agv_handler.state_store.get(sess.agv_id)
            if _st and _st.task_lifecycle:
                cur = str(_st.current_tag or "")
                if sess.delay_s > 0:
                    await asyncio.sleep(sess.delay_s)
                if sess.status == "stopped":
                    return False
                at_dest = (cur == str(dest))
                try:
                    _st.task_lifecycle = None
                    if hasattr(line_agv_handler, "clear_route"):
                        line_agv_handler.clear_route(sess.agv_id)
                    agv_task_queue.on_agv_completed(sess.agv_id, notes="sim:auto_confirm")
                    print(f"[SIM] {sess.agv_id}: ✓ auto-confirm at {cur}")
                except Exception as _e:
                    print(f"[SIM] auto-confirm error: {_e}")
                if at_dest:
                    # Chờ thêm để task_queue settle (tránh race với auto-dispatch)
                    await asyncio.sleep(0.8)
                    return True
                continue
            if _st and str(_st.current_tag or "") == str(dest):
                return True
            if not agv_task_queue.get_running(sess.agv_id):
                await asyncio.sleep(0.5)
                if _st and str(_st.current_tag or "") == str(dest):
                    return True

    # ── Main loop: step-by-step theo sequence ─────────────────────────────
    try:
        while sess.current_cycle < sess.total_cycles:
            if sess.status == "stopped":
                break
            while sess.status == "paused":
                await asyncio.sleep(0.3)

            dest = sess.current_dest
            if not dest:
                break

            label = f"Mô phỏng vòng {sess.current_cycle+1}/{sess.total_cycles}"
            sess.dispatch_count += 1
            print(f"[SIM] {sess.agv_id}: cycle={sess.current_cycle+1} "
                  f"step={sess.current_step}/{len(sess.full_sequence)-1} → {dest}")

            try:
                cmd, dispatched = await asyncio.to_thread(
                    _sim_dispatch, agv_task_queue,
                    sess.agv_id, CMD_GO_TO, dest,
                    sess.session_id, label,
                )
                if not dispatched and getattr(cmd, 'status', '') in ('failed', 'cancelled'):
                    sess.error_count += 1
                    await asyncio.sleep(2)
                    continue
            except Exception as e:
                sess.error_count += 1
                print(f"[SIM] dispatch error → {e!r}")
                await asyncio.sleep(2)
                continue

            ok = await _wait_and_confirm(dest)
            if not ok and sess.status != "stopped":
                sess.error_count += 1

            sess.advance_step()

        if sess.status == "running":
            sess.status = "completed"
            avg = round(sum(sess.cycle_times)/max(len(sess.cycle_times),1), 1) if sess.cycle_times else 0
            print(f"[SIM] {sess.agv_id}: COMPLETED {sess.current_cycle} cycles | avg_cycle={avg}s")

    except asyncio.CancelledError:
        sess.status = "stopped"
        print(f"[SIM] {sess.agv_id}: session cancelled")
    except Exception as e:
        sess.status = "error"
        sess.error_msg = str(e)
        print(f"[SIM] {sess.agv_id}: session error: {e}")
    finally:
        _agv_sessions.pop(sess.agv_id, None)
        _sim_active_agvs.discard(sess.agv_id)
