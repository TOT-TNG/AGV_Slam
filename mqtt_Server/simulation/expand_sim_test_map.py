"""Mở rộng map Sim_test (chỉ trong TOT_AGV_SIM) để đủ chỗ đỗ/sạc cho 15-20 xe.
Thêm 1 "bãi đỗ" dạng thang (ladder) ở vùng trống giữa map + 5 trạm sạc. Chạy lại an toàn (idempotent)."""
import math, sys
import psycopg2, psycopg2.extras
sys.stdout.reconfigure(encoding="utf-8")
DB = "postgresql://postgres:ducmanh1801@localhost:5432/" + (sys.argv[1] if len(sys.argv) > 1 else "TOT_AGV_SIM")  # tham số: tên DB
M = "1791639658147"
XS = [160, 220, 280, 340, 400, 460]
TOP_Y, BOT_Y, CHG_Y = 190, 250, 140
pts, roads = {}, []
def node(nid, x, y, typ, act): pts[nid] = (x, y, typ, act)
base = {"agvCompat": "RFID", "defaultAction": ""}
for i, x in enumerate(XS):
    node(str(201+i), x, TOP_Y, 0, {**base, "locationType": "NORMAL"})
    node(str(211+i), x, BOT_Y, 0, {**base, "locationType": "NORMAL", "waiting_node": "yes"})
for i, x in enumerate(XS):
    if i == 2: continue            # cột 280 là lối vào từ node 98
    node(str(221+i), x, CHG_Y, 2, {**base, "locationType": "CHARGER", "approach_dir": "bwd",
         "turn_allowed": "no", "defaultAction": "CHARGE", "arrival_action": "wait_charge"})
    roads.append((str(221+i), str(201+i)))
for i in range(len(XS)):
    roads += [(str(201+i), str(211+i))]
    if i: roads += [(str(200+i), str(201+i)), (str(210+i), str(211+i))]
roads += [("98", "203"), ("109", "216")]
conn = psycopg2.connect(DB); cur = conn.cursor()
cur.execute("select name_id,x,y from agv_map_points where map_id=%s", (M,))
allp = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
cur.execute("delete from agv_map_points where map_id=%s and name_id=any(%s)", (M, list(pts)))
for nid, (x, y, t, a) in pts.items():
    cur.execute("insert into agv_map_points(map_id,name_id,name,x,y,theta,type,zone,action,carrier,available,accuracy,speed)"
                " values(%s,%s,'',%s,%s,0,%s,'',%s,0,false,0,0.3)", (M, nid, x, y, t, psycopg2.extras.Json(a)))
    allp[nid] = (x, y)
cur.execute("delete from agv_map_roads where map_id=%s and ((id_source=any(%s)) or (id_dest=any(%s)))", (M, list(pts), list(pts)))
for s, d in roads:
    (x1, y1), (x2, y2) = allp[s], allp[d]
    cur.execute("insert into agv_map_roads(map_id,name,id_source,id_dest,point_start_x,point_start_y,point_end_x,point_end_y,"
                "width,speed,move_direction,distance,lidar_off,lidar_off_dir,distance_manual) values(%s,'',%s,%s,%s,%s,%s,%s,0.95,0.5,0,%s,true,'none',false)",
                (M, s, d, x1, y1, x2, y2, round(math.hypot(x2-x1, y2-y1), 2)))
conn.commit(); print("nodes+", len(pts), "roads+", len(roads))
