"""
schedule_manager.py — Quản lý lịch chạy tự động cho AGV.
"""
from __future__ import annotations
import asyncio
import datetime
import json as _json
import uuid
from typing import Optional


# ── Helpers ──────────────────────────────────────────────────────────────────

PRIORITY_LABEL = {1: 'Khẩn cấp', 2: 'Cao', 3: 'Bình thường', 4: 'Thấp', 5: 'Rất thấp'}
WEEKDAY_LABEL  = {1:'T2', 2:'T3', 3:'T4', 4:'T5', 5:'T6', 6:'T7', 7:'CN'}

_TZ = datetime.timezone(datetime.timedelta(hours=7))   # UTC+7


def _now() -> datetime.datetime:
    return datetime.datetime.now(_TZ)


def _to_local(dt: datetime.datetime) -> datetime.datetime:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(_TZ)


# ── ScheduleManager ───────────────────────────────────────────────────────────

class ScheduleManager:
    """
    Lưu lịch vào DB, kiểm tra mỗi 30s, dispatch khi đến hạn.
    """

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS agv_schedules (
        id            TEXT PRIMARY KEY,
        agv_id        TEXT        NOT NULL,
        command       TEXT        NOT NULL,
        map_id        TEXT,
        team_id       INTEGER,
        priority      INTEGER     DEFAULT 3,
        schedule_type TEXT        NOT NULL,
        scheduled_at  TIMESTAMPTZ,
        time_of_day   TEXT,
        days_of_week  INTEGER[],
        interval_minutes INTEGER,
        label         TEXT        DEFAULT '',
        active        BOOLEAN     DEFAULT TRUE,
        created_at    TIMESTAMPTZ DEFAULT NOW(),
        last_run      TIMESTAMPTZ,
        next_run      TIMESTAMPTZ,
        run_count     INTEGER     DEFAULT 0
    )
    """
    ALTER_TABLE_SQL = """
    ALTER TABLE agv_schedules ADD COLUMN IF NOT EXISTS map_id TEXT
    """

    def __init__(self, pool):
        self.pool  = pool
        self._task: Optional[asyncio.Task] = None

    async def init_table(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(self.CREATE_TABLE_SQL)
            await conn.execute(self.ALTER_TABLE_SQL)
        print("[SCHEDULER] table ready")

    # ── next_run computation ─────────────────────────────────────────────────

    def calc_next_run(self, s: dict) -> Optional[datetime.datetime]:
        now   = _now()
        stype = s.get('schedule_type', '')

        if stype == 'once':
            sat = _to_local(s.get('scheduled_at'))
            return sat if sat and sat > now else None

        elif stype == 'daily':
            tod  = s.get('time_of_day') or '08:00'
            days = list(s.get('days_of_week') or range(1, 8))
            try:
                h, m = map(int, tod.split(':'))
            except Exception:
                h, m = 8, 0
            for ahead in range(8):
                cand = now + datetime.timedelta(days=ahead)
                wd   = cand.weekday() + 1   # 1=Mon … 7=Sun
                if wd in days:
                    cdt = cand.replace(hour=h, minute=m, second=0, microsecond=0)
                    if cdt > now:
                        return cdt
            return None

        elif stype == 'interval':
            mins = int(s.get('interval_minutes') or 60)
            last = _to_local(s.get('last_run'))
            if last:
                return last + datetime.timedelta(minutes=mins)
            return now + datetime.timedelta(minutes=mins)

        return None

    # ── Background scheduler ─────────────────────────────────────────────────

    def start(self, loop=None) -> None:
        self._task = asyncio.ensure_future(self._run_loop())
        print("[SCHEDULER] started")

    async def _run_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            try:
                await self._tick()
            except Exception as e:
                print(f"[SCHEDULER] tick error: {e}")

    async def _tick(self) -> None:
        now = _now()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM agv_schedules "
                "WHERE active=TRUE AND next_run IS NOT NULL AND next_run <= $1",
                now,
            )
        for row in rows:
            s = dict(row)
            await self._execute(s)

    async def _execute(self, s: dict) -> None:
        agv_id  = s['agv_id']
        command = s['command']
        map_id  = s.get('map_id')
        team_id = s.get('team_id')
        label   = s.get('label') or f"Lịch {s['id'][:6]}"

        print(f"[SCHEDULER] execute: agv={agv_id} cmd={command} map={map_id} tổ={team_id}")

        try:
            dest_node = None
            if team_id:
                dest_node = await self._resolve_team_node(team_id, agv_id, map_id)
                if not dest_node:
                    print(f"[SCHEDULER] {agv_id}: không tìm được node cho tổ {team_id} map={map_id}")
                    return

            from task_queue import agv_task_queue, CMD_GO_TO, CMD_GO_CHARGE, CMD_GO_WAIT
            sid = uuid.uuid4().hex[:8]

            if command.startswith('wf:'):
                wf_id = command[3:]
                steps = await self._load_wf_steps(wf_id)
                if not steps:
                    print(f"[SCHEDULER] {agv_id}: workflow {wf_id} không có bước hợp lệ")
                    return
                # Dispatch toàn bộ steps trong thread pool (tránh deadlock với plan_path_for_order)
                await asyncio.to_thread(
                    self._dispatch_wf_steps,
                    agv_task_queue, agv_id, steps, dest_node, sid, label,
                )
                print(f"[SCHEDULER] {agv_id}: lịch {s['id'][:8]} → wf {wf_id} ({len(steps)} bước) dest={dest_node}")
            else:
                cmd_map = {'go_to': CMD_GO_TO, 'go_charge': CMD_GO_CHARGE, 'go_wait': CMD_GO_WAIT}
                cmd = cmd_map.get(command, CMD_GO_TO)
                # Phải chạy trong thread pool để tránh deadlock:
                # dispatch_or_queue → plan_path_for_order dùng
                # asyncio.run_coroutine_threadsafe().result() — không thể gọi từ event loop thread
                await asyncio.to_thread(
                    agv_task_queue.dispatch_or_queue,
                    agv_id, cmd, dest_node, None, sid, label,
                )
                print(f"[SCHEDULER] {agv_id}: lịch {s['id'][:8]} → {command} dest={dest_node}")

        except Exception as e:
            print(f"[SCHEDULER] execute error ({s['id'][:8]}): {e}")
            return

        # Cập nhật DB
        now     = _now()
        s_upd   = {**s, 'last_run': now}
        nx_run  = self.calc_next_run(s_upd)
        is_once = s['schedule_type'] == 'once'

        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE agv_schedules "
                "SET last_run=$1, run_count=run_count+1, next_run=$2, active=$3 "
                "WHERE id=$4",
                now, nx_run, (not is_once) and s.get('active', True), s['id'],
            )

    async def _load_wf_steps(self, wf_id: str) -> list:
        """Load workflow template từ DB rồi parse thành danh sách bước."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT steps FROM agv_workflow_templates WHERE template_id=$1", wf_id
                )
            if not row:
                print(f"[SCHEDULER] _load_wf_steps: không tìm thấy template {wf_id}")
                return []
            raw = row['steps']
            if isinstance(raw, str):
                raw = _json.loads(raw)
            return self._parse_wf_steps(raw or [])
        except Exception as e:
            print(f"[SCHEDULER] _load_wf_steps error: {e}")
            return []

    def _parse_wf_steps(self, raw: list) -> list:
        """Tương đương parseWfSteps() trên frontend — trả về [{cmd, needs_dest}]."""
        from task_queue import CMD_GO_TO, CMD_GO_CHARGE, CMD_GO_WAIT
        result = []
        for s in raw:
            t = (s.get('type') or 'move').lower()
            needs_dest = False
            if t in ('move', 'go_to'):
                cmd = CMD_GO_TO; needs_dest = True
            elif t == 'charge':
                cmd = CMD_GO_CHARGE
            elif t in ('wait-zone', 'park'):
                cmd = CMD_GO_WAIT
            elif t == 'wait':
                continue  # timer-wait → bỏ qua
            elif t == 'stop':
                cmd = 'stop'
            elif t == 'resume':
                cmd = 'resume'
            else:
                cmd = CMD_GO_TO; needs_dest = True
            result.append({'cmd': cmd, 'needs_dest': needs_dest})
        return result

    def _dispatch_wf_steps(self, queue, agv_id: str, steps: list,
                           dest_node: Optional[str], sid: str, label: str) -> None:
        """
        Dispatch toàn bộ bước của workflow — phải gọi từ thread pool.
        Bước 0 được dispatch ngay (path-plan), các bước sau enqueue.
        Tất cả dùng cùng session_id để hiển thị nhóm lệnh trên UI.
        """
        for step in steps:
            dn = dest_node if step['needs_dest'] else None
            queue.dispatch_or_queue(agv_id, step['cmd'], dn, None, sid, label)

    async def _resolve_team_node(self, team_id: int, agv_id: str, map_id: Optional[str] = None) -> Optional[str]:
        """Tìm DROPOFF node thuộc team_id dùng cùng điều kiện với /api/execute/team-nodes."""
        try:
            async with self.pool.acquire() as conn:
                if map_id:
                    row = await conn.fetchrow(
                        "SELECT name_id FROM agv_map_points "
                        "WHERE CAST(map_id AS TEXT) = $1 "
                        "  AND action->>'locationType' = 'DROPOFF' "
                        "  AND (action->>'team') IS NOT NULL "
                        "  AND (action->>'team')::int = $2 "
                        "LIMIT 1",
                        str(map_id), team_id,
                    )
                else:
                    row = await conn.fetchrow(
                        "SELECT p.name_id FROM agv_map_points p "
                        "JOIN agv_devices d ON CAST(d.map_id AS TEXT) = CAST(p.map_id AS TEXT) "
                        "WHERE d.name = $1 "
                        "  AND p.action->>'locationType' = 'DROPOFF' "
                        "  AND (p.action->>'team') IS NOT NULL "
                        "  AND (p.action->>'team')::int = $2 "
                        "LIMIT 1",
                        agv_id, team_id,
                    )
            if row:
                print(f"[SCHEDULER] resolve_team_node: tổ {team_id} → node {row['name_id']}")
                return str(row['name_id'])
            print(f"[SCHEDULER] resolve_team_node: không tìm thấy DROPOFF node cho tổ {team_id} map={map_id}")
        except Exception as e:
            print(f"[SCHEDULER] resolve_team_node error: {e}")
        return None

    # ── CRUD ─────────────────────────────────────────────────────────────────

    async def create(self, data: dict) -> dict:
        sid = uuid.uuid4().hex
        nx  = self.calc_next_run(data)
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO agv_schedules "
                "(id,agv_id,command,map_id,team_id,priority,schedule_type,"
                " scheduled_at,time_of_day,days_of_week,interval_minutes,label,next_run) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)",
                sid,
                data['agv_id'],
                data['command'],
                data.get('map_id'),
                data.get('team_id'),
                int(data.get('priority', 3)),
                data['schedule_type'],
                data.get('scheduled_at'),
                data.get('time_of_day'),
                data.get('days_of_week'),
                data.get('interval_minutes'),
                data.get('label', ''),
                nx,
            )
        return {'id': sid, 'next_run': nx.isoformat() if nx else None}

    async def toggle(self, sid: str) -> dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE agv_schedules SET active=NOT active WHERE id=$1 RETURNING *", sid
            )
        if not row:
            return {}
        s = dict(row)
        # Recalculate next_run when re-activating
        if s.get('active'):
            nx = self.calc_next_run(s)
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE agv_schedules SET next_run=$1 WHERE id=$2", nx, sid
                )
            s['next_run'] = nx
        return s

    async def delete(self, sid: str) -> bool:
        async with self.pool.acquire() as conn:
            r = await conn.execute("DELETE FROM agv_schedules WHERE id=$1", sid)
        return r != "DELETE 0"

    async def get_upcoming(self) -> list[dict]:
        """
        Trả về các lịch active, sắp xếp theo next_run (gần → xa).
        Lịch one-time đã chạy (active=False) không hiện.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM agv_schedules "
                "WHERE active=TRUE ORDER BY next_run ASC NULLS LAST"
            )
        result = []
        now = _now()
        for i, row in enumerate(rows):
            s = dict(row)
            nx = _to_local(s.get('next_run'))
            # Phút còn lại đến lần chạy tiếp
            mins_left = None
            if nx:
                delta = nx - now
                mins_left = max(0, int(delta.total_seconds() / 60))
            result.append({
                'id':               s['id'],
                'agv_id':           s['agv_id'],
                'command':          s['command'],
                'team_id':          s.get('team_id'),
                'priority':         s.get('priority', 3),
                'priority_label':   PRIORITY_LABEL.get(s.get('priority', 3), ''),
                'schedule_type':    s['schedule_type'],
                'scheduled_at':     _to_local(s.get('scheduled_at')).isoformat() if s.get('scheduled_at') else None,
                'time_of_day':      s.get('time_of_day'),
                'days_of_week':     list(s.get('days_of_week') or []),
                'days_label':       ' '.join(WEEKDAY_LABEL.get(d,'?') for d in (s.get('days_of_week') or [])),
                'interval_minutes': s.get('interval_minutes'),
                'label':            s.get('label') or '',
                'active':           s.get('active', True),
                'last_run':         _to_local(s.get('last_run')).isoformat() if s.get('last_run') else None,
                'next_run':         nx.isoformat() if nx else None,
                'run_count':        s.get('run_count', 0),
                'mins_left':        mins_left,
                'is_imminent':      i == 0 and mins_left is not None and mins_left <= 60,
            })
        return result


# ── Module singleton ──────────────────────────────────────────────────────────

_manager: Optional[ScheduleManager] = None


def init_scheduler(pool) -> ScheduleManager:
    global _manager
    _manager = ScheduleManager(pool)
    return _manager


def get_scheduler() -> Optional[ScheduleManager]:
    return _manager
