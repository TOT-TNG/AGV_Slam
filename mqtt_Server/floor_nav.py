"""
Điều hướng nhiều tầng (đi thang máy) cho Line AGV.

Bối cảnh: 1 bản đồ có nhiều tầng (map_manager.floors), mỗi tầng là 1 đồ thị con RIÊNG (chưa có cạnh liên
tầng). Thang máy nối các tầng: node loại 'elevator' (action.elevator_id) cùng id ở các tầng khác nhau =
cùng 1 thang; node đó là ĐIỂM TRONG CABIN của thang ở tầng ấy (xem map_manager.elev_nodes).

Module này chỉ làm phần LẬP KẾ HOẠCH: biến 1 lệnh đi tới đích khác tầng thành chuỗi lệnh hàng đợi bình
thường + 3 lệnh thang máy mới (xem elevator_coordinator.py cho phần điều phối thang thật):

    go_to  Q              (nếu xe còn xa thang) đi tới điểm xếp hàng cách node chờ vài node — xe tới thang trước được trước
    elev_book  E@A        ĐẶT thang khi tới điểm xếp hàng (đứng chờ ở đó nếu thang bận) — được cấp khi thang rảnh
    go_to  W_A            xe tới node chờ ngay trước cabin ở tầng đang đứng
    elev_call  E@A        gọi thang tới tầng A + mở cửa (đứng chờ xác nhận "open" — giống xin mở cửa tự động)
    go_to  cabin_A        xe vào cabin
    elev_ride  E@A>B#W_B  đóng cửa, thang chạy tới tầng B, mở cửa; xe được đặt lại vị trí = cabin_B
    go_to  W_B            xe ra khỏi cabin (vào tiến → ra lùi, vào lùi → ra tiến: nhánh "điểm cụt" có sẵn)
    elev_release  E       nhả thang cho xe khác / đóng cửa
    go_to  đích           (hoặc lặp lại cho thang kế nếu phải đổi thang)

Node cabin phải là NODE CỤT (chỉ 1 hàng xóm = node chờ) — cabin 1 cửa, vào hướng nào ra hướng đó.

Cabin DÙNG CHUNG (thang thật: 1 thẻ RFID trong cabin, cùng số ở mọi tầng): vẽ MỘT node, gắn elevator_id, nối cạnh
tới node chờ của từng tầng. map_manager nhận ra (hàng xóm ở ≥2 tầng) → elev_nodes trỏ cùng node cho mọi tầng,
elev_wait[(thang, tầng)] là node chờ; đường đi luôn tính trong 1 tầng (cabin chỉ còn 1 hàng xóm). Tầng hiện tại của
cabin = tầng thang đang đứng (set_cabin_floor, do bridge cập nhật).
"""
from __future__ import annotations

from collections import deque

# Tên lệnh hàng đợi (task_queue.py import lại các hằng này)
CMD_ELEV_BOOK    = "elev_book"
CMD_ELEV_CALL    = "elev_call"
CMD_ELEV_RIDE    = "elev_ride"
CMD_ELEV_RELEASE = "elev_release"
ELEVATOR_COMMANDS = (CMD_ELEV_BOOK, CMD_ELEV_CALL, CMD_ELEV_RIDE, CMD_ELEV_RELEASE)


def _mm():
    from mqtt_client import map_manager
    return map_manager


def multi_floor(mm=None) -> bool:
    mm = mm or _mm()
    return len(getattr(mm, "floors", None) or []) > 1


def floor_of(node, mm=None) -> str:
    """id tầng của node ('' nếu map 1 tầng)."""
    mm = mm or _mm()
    return str((getattr(mm, "node_floor", None) or {}).get(str(node), "")) if multi_floor(mm) else ""


def floor_level(fid: str, mm=None) -> int | None:
    mm = mm or _mm()
    for f in getattr(mm, "floors", None) or []:
        if str(f["id"]) == str(fid):
            return int(f["level"])
    return None


def level_conflict(fid: str, mm=None) -> str | None:
    """Tầng KHÁC có cùng "Số tầng" với `fid` (thang máy dùng số tầng để biết đi đâu → trùng là không phân biệt
    được). Trả tên tầng trùng, None nếu duy nhất."""
    mm = mm or _mm()
    lv = floor_level(fid, mm)
    for f in getattr(mm, "floors", None) or []:
        if str(f["id"]) != str(fid) and int(f["level"]) == lv:
            return str(f["name"])
    return None


def floor_id_of_level(level, mm=None) -> str | None:
    mm = mm or _mm()
    for f in getattr(mm, "floors", None) or []:
        if int(f["level"]) == int(level):
            return str(f["id"])
    return None


def floor_name(fid: str, mm=None) -> str:
    mm = mm or _mm()
    for f in getattr(mm, "floors", None) or []:
        if str(f["id"]) == str(fid):
            return str(f["name"])
    return str(fid)


def cabin_node(elevator_id: str, fid: str, mm=None) -> str | None:
    mm = mm or _mm()
    return (getattr(mm, "elev_nodes", None) or {}).get((str(elevator_id), str(fid)))


def elevator_floors(elevator_id: str, mm=None) -> list[str]:
    """Các tầng thang này dừng (có node cabin), theo thứ tự tầng trong map."""
    mm = mm or _mm()
    order = [str(f["id"]) for f in getattr(mm, "floors", None) or []]
    served = {fid for (eid, fid) in (getattr(mm, "elev_nodes", None) or {}) if eid == str(elevator_id)}
    return [f for f in order if f in served]


def plan_rides(src_floor: str, dst_floor: str, mm=None) -> list[tuple[str, str, str]] | None:
    """Chuỗi chuyến thang ÍT NHẤT để đi từ tầng src tới tầng dst: [(elevator_id, tầng_lên, tầng_xuống), ...].
    Tìm theo chiều rộng trên đồ thị "tầng nối bởi thang". None nếu không có đường."""
    mm = mm or _mm()
    if src_floor == dst_floor:
        return []
    elev_ids = []
    for (eid, _fid) in (getattr(mm, "elev_nodes", None) or {}):
        if eid not in elev_ids:
            elev_ids.append(eid)
    seen = {src_floor}
    q = deque([(src_floor, [])])
    while q:
        f, rides = q.popleft()
        for eid in elev_ids:
            served = elevator_floors(eid, mm)
            if f not in served:
                continue
            for g in served:
                if g in seen:
                    continue
                nr = rides + [(eid, f, g)]
                if g == dst_floor:
                    return nr
                seen.add(g)
                q.append((g, nr))
    return None


def is_shared_cabin(node, mm=None) -> bool:
    """Node cabin DÙNG CHUNG cho nhiều tầng (1 thẻ RFID, cạnh nối node chờ của từng tầng)."""
    mm = mm or _mm()
    return str(node) in (getattr(mm, "shared_cabins", None) or ())


def wait_node(elevator_id: str, fid: str, mm=None) -> str | None:
    """Node chờ ngay trước cabin ở tầng `fid` (hàng xóm của cabin dùng chung trên tầng đó); None nếu cabin không
    dùng chung (khi đó suy ra từ đường đi tới cabin)."""
    mm = mm or _mm()
    return (getattr(mm, "elev_wait", None) or {}).get((str(elevator_id), str(fid)))


def set_cabin_floor(node, fid: str, mm=None) -> None:
    """Cabin dùng chung nằm ở tầng nào lúc này = tầng thang đang đứng (1 xe/thang). Bridge cập nhật khi cabin mở
    cửa đón xe (tầng nguồn) và khi thang tới nơi (tầng đích) để floor_of(cabin) đúng với mọi chỗ tra cứu tầng của xe,
    và toạ độ của cabin = vị trí mặt cabin ở tầng đó (hướng rẽ tại node chờ tính theo toạ độ node trước nó)."""
    mm = mm or _mm()
    nf = getattr(mm, "node_floor", None)
    if nf is not None and is_shared_cabin(node, mm) and fid:
        nf[str(node)] = str(fid)
        xy = (getattr(mm, "cabin_xy", None) or {}).get(str(node), {}).get(str(fid))
        if xy:
            for d in (getattr(mm, "points", None), getattr(mm, "line_points", None)):
                if isinstance(d, dict) and str(node) in d:
                    d[str(node)] = (float(xy[0]), float(xy[1]))


# ── Cửa cabin: hướng vào / ra ──────────────────────────────────────────────────
# Mỗi mặt cabin (mỗi tầng) khai báo CẠNH có cửa trong khung CỐ ĐỊNH của cabin: N, E, S, W (nhìn từ trên xuống,
# theo chiều kim đồng hồ). Từ cạnh cửa vào/ra suy ra xe phải ra thế nào (xem plan_cabin_exit). Chưa khai báo cạnh
# → coi như cùng 1 cạnh (cabin 1 cửa): lùi ra đúng đường đã vào — hành vi cũ.
DOORS = ("N", "E", "S", "W")


def cabin_door(cabin, fid: str, mm=None) -> str:
    """Cạnh cửa của cabin dùng chung ở tầng `fid` ('N'|'E'|'S'|'W'), '' nếu chưa khai báo."""
    mm = mm or _mm()
    cfg = (getattr(mm, "node_actions", None) or {}).get(str(cabin)) or {}
    d = str(((cfg.get("cabin_doors") if isinstance(cfg, dict) else None) or {}).get(str(fid), "")).strip().upper()
    return d if d in DOORS else ""


def can_rotate(agv_id: str) -> bool:
    """Xe có quay tại chỗ trong cabin được không. Rơ-moóc (type 'trailer') và mọi xe không lùi được (xe kéo kèm
    rơ-moóc) thì KHÔNG; xe carry / xe kéo không rơ-moóc lùi được thì có."""
    try:
        from agv_registry import agv_registry as _reg
        return bool(_reg.can_reverse(agv_id)) and str(_reg.get_type(agv_id) or "").lower() != "trailer"
    except Exception:
        return True


def plan_cabin_exit(door_in: str, door_out: str, d_in: str, can_reverse: bool = True,
                    can_rotate_: bool = True) -> dict | None:
    """Cách xe ra khỏi cabin, tính trong khung cabin (N,E,S,W theo chiều kim đồng hồ).

    Vào TIẾN (mũi dẫn đầu): mũi xe hướng vào trong = ngược cạnh cửa vào. Vào LÙI: mũi hướng ra cạnh cửa vào.
    Ra: chạy tới cạnh `door_out` — bằng TIẾN (mũi hướng cạnh đó) hoặc LÙI (đuôi hướng cạnh đó). Quay tại chỗ theo
    bội 90° (TURN_R = +90° kim đồng hồ, TURN_L = -90°). Rẽ trong cabin CHỈ làm khi không đổi chiều tiến/lùi
    (đổi chiều sau TURN cần thêm WAIT_SYS — không có trong cabin vì xe mất mạng khi cửa đóng), nên ra bằng cùng chiều
    với lúc vào nếu phải quay. Chọn phương án quay ÍT nhất; hoà thì ưu tiên ra TIẾN (lidar nhìn về hướng đi).

    Trả {'exit_dir': 'fwd'|'bwd', 'turns': [TURN...], 'quarter': 0..3, 'kind': 'reverse'|'straight'|'turn'} hoặc
    None nếu xe không làm được (vd rơ-moóc: chỉ đi thẳng xuyên qua cabin cửa đối diện)."""
    di, do = DOORS.index(door_in), DOORS.index(door_out)
    heading = (di + 2) % 4 if d_in == "fwd" else di
    best = None
    for exit_dir in ("fwd", "bwd"):
        if exit_dir == "bwd" and not can_reverse:
            continue
        target = do if exit_dir == "fwd" else (do + 2) % 4
        q = (target - heading) % 4                       # số góc 90° quay theo chiều kim đồng hồ
        if q and (not can_rotate_ or exit_dir != d_in):
            continue
        cost = 0 if q == 0 else (2 if q == 2 else 1)
        key = (cost, 0 if exit_dir == "fwd" else 1)
        if best is None or key < best[0]:
            best = (key, exit_dir, q)
    if best is None:
        return None
    _, exit_dir, q = best
    turns = ["R"] if q == 1 else (["L"] if q == 3 else (["L", "L"] if q == 2 else []))
    kind = "turn" if q else ("reverse" if exit_dir != d_in else "straight")
    return {"exit_dir": exit_dir, "turns": turns, "quarter": q, "kind": kind}


def cabin_exit_for(eid: str, fa: str, fb: str, d_in: str, agv_id: str, mm=None) -> dict | None:
    """plan_cabin_exit cho chuyến thang fa→fb của xe `agv_id`; cạnh cửa chưa khai báo → cùng cạnh (lùi ra)."""
    mm = mm or _mm()
    cab = cabin_node(eid, fa, mm)
    da, db = (cabin_door(cab, fa, mm), cabin_door(cab, fb, mm)) if cab else ("", "")
    if not da or not db:
        da = db = "N"
    try:
        from agv_registry import agv_registry as _reg
        rev = bool(_reg.can_reverse(agv_id))
    except Exception:
        rev = True
    return plan_cabin_exit(da, db, d_in, can_reverse=rev, can_rotate_=can_rotate(agv_id))


def _path(a: str, b: str, what: str, mm, floor: str | None = None) -> list[str]:
    if floor is not None and getattr(mm, "shared_cabins", None):
        p = mm.line_shortest_path(str(a), str(b), floor=str(floor))
    else:
        p = mm.line_shortest_path(str(a), str(b))
    if not p or len(p) < 1:
        raise ValueError(f"Không có đường từ node {a} tới {what} {b}")
    return [str(x) for x in p]


def exit_corridor(cab: str, w: str, mm=None, max_len: int = 8, eid: str | None = None, fid: str | None = None) -> list[str]:
    """Hành lang xe đi qua khi RA khỏi cabin: cabin → node thoát `w` → ... → ngã ba (degree≥3) đầu tiên (bao gồm).
    Xe chỉ coi là THOÁT KHỎI KHU VỰC THANG khi tới 1 node NGOÀI hành lang này (đã đi qua ngã ba). Không có ngã ba trong
    `max_len` node (đường thẳng/cụt) → chỉ {cabin, w}: xe rời node thoát là đã thoát."""
    mm = mm or _mm()
    g = getattr(mm, "line_graph", None) or getattr(mm, "graph", None)
    out = [str(cab), str(w)]
    if eid and fid:
        best = None
        for mk in exit_nodes(eid, fid, mm):        # mốc thoát thủ công: hành lang = cabin → ... TRƯỚC mốc; tới mốc là đã thoát
            try:
                p = [str(x) for x in (mm.line_shortest_path(str(cab), mk, floor=str(fid)) if getattr(mm, "shared_cabins", None)
                                      else mm.line_shortest_path(str(cab), mk))]
            except Exception:
                p = None
            if p and len(p) >= 2 and str(w) in p and (best is None or len(p) < len(best)):
                best = p                           # node khai báo gần cabin nhất theo hướng ra = mốc thoát
        if best:
            return best[:-1]
    if g is None:
        return out

    def _nb(n):
        try:
            return set(g.successors(n)) | set(g.predecessors(n))
        except Exception:
            return set(g[n])
    prev, cur = str(cab), str(w)
    walk = [str(cab), str(w)]
    for _ in range(max_len):
        nbs = {str(x) for x in _nb(cur)}
        if len(nbs) >= 3:
            return walk                       # cur là ngã ba: hành lang kết thúc ở đây (bao gồm ngã ba)
        nxt = [n for n in nbs if n != prev]
        if len(nxt) != 1:
            break                             # cụt (hoặc rẽ lạ) mà chưa gặp ngã ba
        prev, cur = cur, nxt[0]
        walk.append(cur)
    return out


def queue_nodes(elevator_id: str, fid: str, mm=None) -> list[str]:
    """Điểm xếp hàng khai báo thủ công trong Map Editor cho (thang, tầng)."""
    mm = mm or _mm()
    return list((getattr(mm, "elev_queue", None) or {}).get((str(elevator_id), str(fid))) or [])


def exit_nodes(elevator_id: str, fid: str, mm=None) -> list[str]:
    """Mốc thoát khai báo thủ công trong Map Editor cho (thang, tầng)."""
    mm = mm or _mm()
    return list((getattr(mm, "elev_exit", None) or {}).get((str(elevator_id), str(fid))) or [])


def _manual_queue_points(path: list[str], eid: str, fid: str, mm) -> list[str] | None:
    """Điểm xếp hàng thủ công nằm TRÊN đường tới cabin (không tính 2 node cuối: node chờ + cabin), gần cabin nhất trước.
    None nếu người dùng chưa khai báo điểm nào cho thang/tầng này (→ dùng cách tự suy); [] nếu đã khai báo nhưng đường
    này không đi qua điểm nào (xe đặt thang tại chỗ)."""
    declared = queue_nodes(eid, fid, mm)
    if not declared:
        return None
    on_path = {str(n): i for i, n in enumerate(path[:-2])}
    cands = [n for n in declared if n in on_path and on_path[n] > 0]      # >0: không phải chỗ xe đang đứng
    return sorted(cands, key=lambda n: -on_path[n])


def _with_parallel_points(on_path: list[str], pos: str, w: str, eid: str, fid: str, mm) -> list[str]:
    """Điểm xếp hàng khai báo thủ công gồm CẢ các điểm NGOÀI đường ngắn nhất của xe (nhánh song song, vd node 28 bên cạnh
    node 6 cùng dẫn vào node chờ) — các điểm này có chức năng giống nhau, xe sau sang điểm còn trống thay vì chen chỗ.
    Chỉ nhận điểm xe tới được và từ đó tới được node chờ `w`. Sắp theo khoảng cách tới node chờ (gần cabin trước)."""
    decl = [str(n) for n in queue_nodes(eid, fid, mm)]

    def _len(a, b):
        try:
            if getattr(mm, "shared_cabins", None):
                pth = mm.line_shortest_path(str(a), str(b), floor=str(fid))
            else:
                pth = mm.line_shortest_path(str(a), str(b))
            return len(pth) if pth else None
        except Exception:
            return None
    cands = list(on_path)
    for n in decl:
        if n in cands or n == str(pos) or n == str(w):
            continue
        if _len(pos, n) is not None and _len(n, w) is not None:
            cands.append(n)
    return sorted(cands, key=lambda n: (_len(n, w) if _len(n, w) is not None else 10 ** 6))


def _queue_point(path: list[str], mm) -> str | None:
    """Điểm xếp hàng trên đường tới cabin: node NGAY TRƯỚC ngã ba (degree≥3) gần node chờ nhất trên đường đi,
    tức là xe chờ nằm NGOÀI hành lang dẫn vào thang. Hành lang đó (node chờ → ngã ba) là lối ra DUY NHẤT của xe
    vừa xuống thang — xe xếp hàng đứng trong đó sẽ đối đầu với xe ra (kẹt head-on, không bên nào lùi được).
    Đứng ở nhánh trước ngã ba thì xe ra đi qua ngã ba thoải mái. None nếu đường tới thang là 1 chuỗi thẳng không có
    ngã ba (không có chỗ chờ an toàn) hoặc xe đang đứng ngay ngã ba/node có hành vi riêng → đặt thang luôn tại chỗ."""
    g = getattr(mm, "line_graph", None) or getattr(mm, "graph", None)
    if g is None or len(path) < 3:
        return None
    na = getattr(mm, "node_actions", None) or {}

    def _deg(n):
        try:
            return len(set(g.successors(n)) | set(g.predecessors(n)))
        except Exception:
            return len(set(g[n]))
    for j in range(len(path) - 2, 0, -1):
        if _deg(path[j]) >= 3:
            q = str(path[j - 1])
            cfg = na.get(q) or {}
            loc = str(cfg.get("locationType") or "").upper()
            if (not cfg.get("arrival_action") and not cfg.get("door_id") and loc in ("", "NORMAL")
                    and str(cfg.get("trailer_staging") or "").lower() != "yes"
                    and str(cfg.get("trailer_empty_staging") or "").lower() != "yes"):
                return q
            return None
    return None


def _hold_behind(path: list[str], q: str, mm) -> str | None:
    """Chỗ chờ NGAY SAU điểm xếp hàng `q` (trên đường tới cabin) cho xe tới sau khi `q` đã có xe khác giữ chỗ: node thường
    gần `q` nhất ở phía trước, không phải chỗ xe đang đứng (index 0). None nếu không có (xe đã ở sát sau điểm xếp hàng).
    Xe vẫn PHẢI đi tới chỗ này rồi mới đặt thang (đặt thang theo thứ tự TỚI NƠI, không đặt từ xa)."""
    na = getattr(mm, "node_actions", None) or {}
    try:
        idx = [str(n) for n in path].index(str(q))
    except ValueError:
        return None
    for j in range(idx - 1, 0, -1):
        n = str(path[j])
        cfg = na.get(n) or {}
        loc = str(cfg.get("locationType") or "").upper()
        if (not cfg.get("arrival_action") and not cfg.get("door_id") and loc in ("", "NORMAL")
                and str(cfg.get("trailer_staging") or "").lower() != "yes"
                and str(cfg.get("trailer_empty_staging") or "").lower() != "yes"):
            return n
    return None


def decompose(agv_id: str, cur: str, dest: str, mm=None) -> list[tuple[str, str]]:
    """Chuỗi bước [(lệnh, dest_node)] đi từ `cur` tới `dest` KHÁC TẦNG (xem docstring module). Bước đầu
    tiên là đi tới ĐIỂM XẾP HÀNG (nhánh ngay trước ngã ba dẫn vào hành lang thang), tới nơi mới ('elev_book', 'E@tầng') — XE NÀO TỚI TRƯỚC
    ĐƯỢC THANG TRƯỚC (đặt thang theo thứ tự tới nơi, không theo thứ tự ra lệnh), xe tới sau đứng ở điểm xếp hàng
    nhường (cabin 1 cửa: lối ra duy nhất của xe trong thang đi qua đúng node chờ nên không được chờ ở đó).
    Xe đã ở gần thang thì đặt thang luôn.
    ValueError nếu không đi được (thiếu thang/không có đường)."""
    mm = mm or _mm()
    fa, fb = floor_of(cur, mm), floor_of(dest, mm)
    rides = plan_rides(fa, fb, mm)
    if rides is None:
        raise ValueError(
            f"Không có thang máy nối {floor_name(fa, mm)} → {floor_name(fb, mm)} "
            f"(kiểm tra node Elevator + chọn thang ở cả hai tầng)")
    for (eid, a, b) in rides:
        for fid in (a, b):
            other = level_conflict(fid, mm)
            if other:
                raise ValueError(
                    f"Số tầng {floor_level(fid, mm)} của {floor_name(fid, mm)} trùng với {other} — thang máy không "
                    f"phân biệt được 2 tầng này; sửa \"Số tầng\" trong Map Editor rồi Lưu lại")
    # Xe có ra khỏi cabin được không (cạnh cửa vào/ra + khả năng lùi/quay của xe). Hướng vào chưa biết lúc lập chuỗi
    # → phải ra được với MỌI hướng vào mà xe có thể dùng (xe không lùi được chỉ vào TIẾN).
    try:
        from agv_registry import agv_registry as _reg_cx
        _can_rev = bool(_reg_cx.can_reverse(agv_id))
    except Exception:
        _can_rev = True
    for (eid, a, b) in rides:
        for d_in in (("fwd", "bwd") if _can_rev else ("fwd",)):
            if cabin_exit_for(eid, a, b, d_in, agv_id, mm) is None:
                raise ValueError(
                    f"{agv_id}: xe không ra được cabin thang {eid} từ {floor_name(a, mm)} sang {floor_name(b, mm)} "
                    f"(xe không lùi/quay được trong cabin — cần cửa ra ĐỐI DIỆN cửa vào; khai báo cạnh cửa trong Map Editor)")
    steps: list[tuple[str, str]] = []
    pos = str(cur)
    for i, (eid, a, b) in enumerate(rides):
        cab_a, cab_b = cabin_node(eid, a, mm), cabin_node(eid, b, mm)
        if pos == cab_a:
            raise ValueError(f"Xe đang ở trong cabin thang {eid} (node {cab_a}) — đưa xe ra khỏi thang trước")
        # node chờ ngay trước cabin ở tầng a: node liền trước cabin trên đường từ vị trí hiện tại
        p_a = _path(pos, cab_a, "cabin thang", mm, floor=a)
        w_a = wait_node(eid, a, mm) or (p_a[-2:][0] if pos != cab_a else pos)
        q_a = None
        if i == 0 and pos != cab_a:
            from elevator_coordinator import elevator_coordinator as _ec
            manual = _manual_queue_points(p_a, eid, a, mm)
            if manual is not None:
                manual = _with_parallel_points(manual, pos, w_a, eid, a, mm)
            if manual is None:
                q_a = _queue_point(p_a, mm)                    # chưa khai báo thủ công → tự suy từ ngã ba
                if q_a and not _ec.claim_queue_point(eid, a, agv_id):
                    # Điểm xếp hàng đã có xe khác → xe này đứng CHỜ SAU nó, đặt thang khi TỚI NƠI (không đặt từ xa,
                    # không chen hàng trước xe đã tới gần hơn). Không có chỗ chờ phía trước → đã sát sau điểm xếp hàng.
                    q_a = _hold_behind(p_a, q_a, mm)
            else:
                # nhiều điểm xếp hàng cùng chức năng: LƯỢT 1 chọn điểm còn trống VÀ đường tới đó không bị xe khác chiếm
                # (xe khác đang/sắp đi qua đoạn đó dù chưa tới điểm) → sang điểm khác; LƯỢT 2 chỉ cần còn trống.
                def _approach_busy(cand):
                    try:
                        from line_agv_handler import path_claimed_by_other as _pcb, line_agv_handler as _lah_ab
                        # Dùng ĐÚNG đường lệnh sẽ chạy (có xét hướng mũi xe/prev_tag), không phải đường ngắn nhất thuần —
                        # tránh báo "bị chiếm" nhầm (PHÁT HIỆN THỰC TẾ 2026-11-20: điểm 28 bị báo bận dù đường thật thông).
                        _ap = None
                        try:
                            _st_ab = _lah_ab.state_store.get(agv_id)
                            _pv = getattr(_st_ab, 'prev_tag', None) if _st_ab else None
                            if _pv is not None and str(_pv) != str(pos):
                                from agv_registry import agv_registry as _reg_ab
                                _dp = mm.line_directional_path(str(pos), str(cand), str(_pv),
                                                               can_reverse=_reg_ab.can_reverse(agv_id))
                                if _dp and len(_dp) >= 2:
                                    _ap = [str(x) for x in _dp]
                        except Exception:
                            _ap = None
                        if _ap is None:
                            _ap = _path(pos, cand, "điểm xếp hàng", mm, floor=a)
                        return _pcb(agv_id, _ap[1:])
                    except Exception:
                        return None
                for cand in manual:
                    _b = _approach_busy(cand)
                    if _b:
                        print(f"[ELEVATOR] {eid}: đường tới điểm xếp hàng {cand} đang bị {_b} chiếm — {agv_id} thử điểm khác")
                        continue
                    if _ec.claim_queue_point(eid, a, agv_id, node=cand):
                        q_a = cand
                        break
                if q_a is None:
                    for cand in manual:                        # xe sau đứng điểm xa hơn, nối đuôi nhau
                        if _ec.claim_queue_point(eid, a, agv_id, node=cand):
                            q_a = cand
                            break
                if q_a is None and manual:                     # mọi điểm đã có xe → nối đuôi ở điểm XA cabin nhất
                    q_a = manual[-1]
        # node ngay sau cabin ở tầng b, hướng về mục tiêu kế (cabin thang kế hoặc đích)
        target = dest if i == len(rides) - 1 else cabin_node(rides[i + 1][0], rides[i + 1][1], mm)
        pb = _path(cab_b, target, "mục tiêu sau thang", mm, floor=b)
        if len(pb) < 2:
            raise ValueError(f"Node cabin {cab_b} trùng mục tiêu {target}")
        w_b = pb[1]
        if q_a:
            steps.append(("go_to", q_a))
        steps += [
            (CMD_ELEV_BOOK, f"{eid}@{a}"),
            ("go_to", w_a),
            (CMD_ELEV_CALL, f"{eid}@{a}"),
            ("go_to", cab_a),
            (CMD_ELEV_RIDE, f"{eid}@{a}>{b}#{w_b}"),
            ("go_to", w_b),
            (CMD_ELEV_RELEASE, eid),
        ]
        pos = w_b
    steps.append(("go_to", str(dest)))
    return steps


def parse_call(arg: str) -> tuple[str, str]:
    """'E1@F1' → ('E1','F1')"""
    e, _, f = str(arg).partition("@")
    return e, f


def parse_ride(arg: str) -> tuple[str, str, str, str]:
    """'E1@F1>F3#17' → ('E1','F1','F3','17')  (node_ra có thể rỗng)"""
    head, _, w = str(arg).partition("#")
    e, _, ff = head.partition("@")
    a, _, b = ff.partition(">")
    return e, a, b, w
