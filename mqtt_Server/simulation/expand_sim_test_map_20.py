"""Bổ sung bãi đỗ thứ 2 cho Sim_test để đủ chỗ đỗ/siding cho 20 xe.
Chỉ THÊM node 241-252 (lưới 3 cột x 4 hàng) ở vùng trống x 690-819, y 190-340 và nối vào
node 232 / 18 (cột x=614). KHÔNG đụng node/road cũ => an toàn với phần đã sửa tay.
Chạy lại an toàn (idempotent). Tham số: tên DB (mặc định TOT_AGV_SIM)."""
import math, sys
import psycopg2, psycopg2.extras
sys.stdout.reconfigure(encoding="utf-8")
DB = "postgresql://postgres:ducmanh1801@localhost:5432/" + (sys.argv[1] if len(sys.argv) > 1 else "TOT_AGV_SIM")
M = "1791639658147"
XS = [690, 755, 819]
YS = [190, 240, 290, 340]
base = {"agvCompat": "RFID", "defaultAction": "", "locationType": "NORMAL"}
pts, grid = {}, {}
nid = 241
for r, y in enumerate(YS):
    for c, x in enumerate(XS):
        act = dict(base)
        if r > 0:
            act["waiting_node"] = "yes"
        pts[str(nid)] = (x, y, 0, act)
        grid[(r, c)] = str(nid)
        nid += 1
roads = []
for r in range(len(YS)):
    for c in range(len(XS)):
        if c: roads.append((grid[(r, c - 1)], grid[(r, c)]))
        if r: roads.append((grid[(r - 1, c)], grid[(r, c)]))
roads += [("232", grid[(0, 0)]), ("18", grid[(2, 0)])]   # 2 lối vào -> có vòng, không dead-end

conn = psycopg2.connect(DB); cur = conn.cursor()
cur.execute("select name_id,x,y from agv_map_points where map_id=%s", (M,))
allp = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
for k in ("232", "18"):
    assert k in allp, f"thiếu node {k} trong {DB}"
cur.execute("delete from agv_map_points where map_id=%s and name_id=any(%s)", (M, list(pts)))
for k, (x, y, t, a) in pts.items():
    cur.execute("insert into agv_map_points(map_id,name_id,name,x,y,theta,type,zone,action,carrier,available,accuracy,speed)"
                " values(%s,%s,'',%s,%s,0,%s,'',%s,0,false,0,0.3)", (M, k, x, y, t, psycopg2.extras.Json(a)))
    allp[k] = (x, y)
cur.execute("delete from agv_map_roads where map_id=%s and (id_source=any(%s) or id_dest=any(%s))", (M, list(pts), list(pts)))
for s, d in roads:
    (x1, y1), (x2, y2) = allp[s], allp[d]
    cur.execute("insert into agv_map_roads(map_id,name,id_source,id_dest,point_start_x,point_start_y,point_end_x,point_end_y,"
                "width,speed,move_direction,distance,lidar_off,lidar_off_dir,distance_manual) values(%s,'',%s,%s,%s,%s,%s,%s,0.95,0.5,0,%s,true,'none',false)",
                (M, s, d, x1, y1, x2, y2, round(math.hypot(x2 - x1, y2 - y1), 2)))
conn.commit(); print(DB, "nodes+", len(pts), "roads+", len(roads))
