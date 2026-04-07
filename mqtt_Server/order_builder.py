import uuid
from datetime import timezone, datetime


def iso_ts_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_order(
    agv_id: str,
    path: list,
    coords: dict = None,
    manufacture: str = "TNG:TOT",
    SerialNumber: str = None,
    version: str = "2.0",
    order_id: str = None,
    order_update_id: int = 0,
    horizon: int = None,
):
    """
    Build VDA5050 order v?i full path.
    - path: danh s?ch nodeId theo th? t?.
    - coords: dict {nodeId: (x,y[,theta]) ho?c {x,y,theta}} ?? nh?ng nodePosition.
    - horizon: s? node release tr??c; None ho?c >=len(path) -> release to?n b?.
    """
    if order_id is None:
        order_id = str(uuid.uuid4())
    if not path or len(path) < 2:
        raise ValueError("Path must have at least 2 nodes")

    release_all = horizon is None or horizon >= len(path)
    released_nodes = path if release_all else path[: max(1, horizon)]

    header = {
        "headerId": uuid.uuid4().hex,
        "timestamp": iso_ts_now(),
        "version": version,
        "manufacturer": manufacture or "TNG:TOT",
        "serialNumber": SerialNumber or agv_id,
        "orderId": order_id,
        "orderUpdateId": order_update_id,
        "orderStatus": "NEW",
    }

    def node_position(node_id):
        if not coords:
            return {}
        if node_id not in coords:
            return {}
        val = coords[node_id]
        if isinstance(val, (list, tuple)):
            if len(val) >= 3:
                return {"x": float(val[0]), "y": float(val[1]), "theta": float(val[2])}
            if len(val) >= 2:
                return {"x": float(val[0]), "y": float(val[1]), "theta": 0.0}
        if isinstance(val, dict):
            return {
                "x": float(val.get("x", 0)),
                "y": float(val.get("y", 0)),
                "theta": float(val.get("theta", 0)),
            }
        return {}

    nodes = []
    seq = 0
    for node_id in path:
        released = release_all or (node_id in released_nodes)
        nodes.append(
            {
                "nodeId": str(node_id),
                "sequenceId": seq,
                "released": released,
                "nodePosition": node_position(node_id),
                "actions": [],
            }
        )
        seq += 2

    edges = []
    seq = 1
    for i in range(len(path) - 1):
        start = str(path[i])
        end = str(path[i + 1])
        released = release_all or (start in released_nodes)
        edges.append(
            {
                "edgeId": f"{start}_to_{end}",
                "sequenceId": seq,
                "startNodeId": start,
                "endNodeId": end,
                "released": released,
                "actions": [],
                "trajectory": {},
            }
        )
        seq += 2

    return {**header, "nodes": nodes, "edges": edges}
