"""
persistent_flags.py — Cờ trạng thái nằm trong RAM nhưng được GHI XUYÊN DB để khôi phục sau khi server khởi động lại.

Các tập cờ (agv, node) như `_pending_empty_pickup_legs`, `_pending_confirm_only_legs`, `_pending_staging_transits`, theo dõi
lấy hàng theo lượt (session) và ngữ cảnh chuyến thang đều là "ghi nhớ giữa 2 lệnh" — mất khi server khởi động lại thì xe làm
nốt lệnh dang dở sẽ hành xử sai (bỏ qua bước lấy rỗng, dừng thêm 1 lần, không biết chiều ra khỏi cabin...).

Bảng agv_runtime_flags(kind, grp, key): mỗi dòng 1 phần tử. Ghi bất đồng bộ, TUẦN TỰ (1 khoá asyncio) nên add→discard liên tiếp
không bị đảo thứ tự. Khi chưa gắn pool (test / trước khi DB sẵn sàng) mọi thao tác chỉ chạy trong RAM như cũ.
"""
from __future__ import annotations

import asyncio
from typing import Iterable, Optional

TABLE = "agv_runtime_flags"


class FlagStore:
    def __init__(self) -> None:
        self._pool = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock: Optional[asyncio.Lock] = None

    # ── gắn DB ─────────────────────────────────────────────────────────────────
    def set_pool(self, pool) -> None:
        self._pool = pool
        try:
            self._loop = asyncio.get_running_loop()
            self._lock = asyncio.Lock()
        except RuntimeError:
            self._loop = None

    @staticmethod
    async def ensure_table(conn) -> None:
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                kind        TEXT NOT NULL,
                grp         TEXT NOT NULL,
                key         TEXT NOT NULL,
                created_at  TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (kind, grp, key)
            )""")

    # ── ghi (bất đồng bộ, tuần tự) ─────────────────────────────────────────────
    def _run(self, *stmts) -> None:
        """stmts: các (sql, *args) chạy tuần tự trong 1 giao dịch."""
        if self._pool is None:
            return

        async def _do() -> None:
            try:
                async with self._lock:
                    async with self._pool.acquire() as conn:
                        async with conn.transaction():
                            for sql, *args in stmts:
                                await conn.execute(sql, *args)
            except Exception as e:
                print(f"[FLAGS] ghi DB lỗi: {type(e).__name__}: {e}")

        try:
            asyncio.get_running_loop().create_task(_do())
        except RuntimeError:
            if self._loop is not None and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(_do(), self._loop)

    def add(self, kind: str, grp: str, key: str) -> None:
        self._run((f"INSERT INTO {TABLE}(kind,grp,key) VALUES($1,$2,$3) ON CONFLICT DO NOTHING", kind, str(grp), str(key)))

    def discard(self, kind: str, grp: str, key: str) -> None:
        self._run((f"DELETE FROM {TABLE} WHERE kind=$1 AND grp=$2 AND key=$3", kind, str(grp), str(key)))

    def remove_group(self, kind: str, grp: str) -> None:
        self._run((f"DELETE FROM {TABLE} WHERE kind=$1 AND grp=$2", kind, str(grp)))

    def remove_kind(self, kind: str) -> None:
        self._run((f"DELETE FROM {TABLE} WHERE kind=$1", kind))

    def replace(self, kind: str, grp: str, key: str) -> None:
        """Mỗi (kind, grp) chỉ giữ 1 giá trị: xoá giá trị cũ rồi ghi giá trị mới (cùng 1 giao dịch)."""
        self._run((f"DELETE FROM {TABLE} WHERE kind=$1 AND grp=$2", kind, str(grp)),
                  (f"INSERT INTO {TABLE}(kind,grp,key) VALUES($1,$2,$3) ON CONFLICT DO NOTHING", kind, str(grp), str(key)))

    # ── đọc (lúc khởi động) ────────────────────────────────────────────────────
    @staticmethod
    async def load(conn, kinds: Iterable[str]) -> list:
        rows = await conn.fetch(f"SELECT kind, grp, key FROM {TABLE} WHERE kind = ANY($1::text[])", list(kinds))
        return [(r["kind"], r["grp"], r["key"]) for r in rows]

    @staticmethod
    async def purge(conn, keep_groups_by_kind: dict, max_age_s: float) -> None:
        """Xoá cờ quá cũ, và cờ của (kind, grp) KHÔNG nằm trong danh sách giữ (AGV/session đã hết lệnh)."""
        await conn.execute(f"DELETE FROM {TABLE} WHERE created_at < NOW() - make_interval(secs => $1::double precision)",
                           float(max_age_s))
        for kind, groups in keep_groups_by_kind.items():
            await conn.execute(f"DELETE FROM {TABLE} WHERE kind=$1 AND NOT (grp = ANY($2::text[]))", kind, list(groups))


flag_store = FlagStore()


class PersistentPairSet(set):
    """set[(agv_id, node)] có ghi xuyên DB. Chỉ các thao tác dùng trong code (add/discard/remove/clear/pop/update) được ghi."""

    def __init__(self, kind: str) -> None:
        super().__init__()
        self._kind = kind

    def load(self, pairs: Iterable) -> None:
        """Nạp từ DB (không ghi ngược)."""
        for a, b in pairs:
            set.add(self, (str(a), str(b)))

    def add(self, item) -> None:
        new = item not in self
        set.add(self, item)
        if new:
            flag_store.add(self._kind, item[0], item[1])

    def discard(self, item) -> None:
        if item in self:
            set.discard(self, item)
            flag_store.discard(self._kind, item[0], item[1])

    def remove(self, item) -> None:
        set.remove(self, item)
        flag_store.discard(self._kind, item[0], item[1])

    def pop(self):
        item = set.pop(self)
        flag_store.discard(self._kind, item[0], item[1])
        return item

    def clear(self) -> None:
        if self:
            set.clear(self)
            flag_store.remove_kind(self._kind)

    def update(self, *others) -> None:
        for o in others:
            for item in o:
                self.add(item)
