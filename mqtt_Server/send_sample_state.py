from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request


SERVER_BASE_URL = "http://192.168.88.253:8000"


SCENARIOS: dict[str, list[dict[str, object]]] = {
    "corridor_wait": [
        # Dua AGV03 vao N21 truoc, sau do AGV01 di qua N21 de test WAIT.
        {
            "agv_id": "AGV03",
            "destination": "21",
            "path": ["3", "18", "17", "21"],
            "wait_before": 0.0,
            "note": "AGV03 chiem N21",
        },
        {
            "agv_id": "AGV01",
            "destination": "20",
            "path": ["1", "2", "3", "18", "17", "21", "20"],
            "wait_before": 2.0,
            "note": "AGV01 buoc di qua N21 de gap AGV03",
        },
    ],
    "triple_conflict": [
        # AGV03 giu N21. AGV01 co y di qua N21 den N20.
        # Neu AGV01 bi reroute sang nhanh N23 thi AGV02 da chiem N23 san.
        {
            "agv_id": "AGV03",
            "destination": "21",
            "path": ["3", "18", "17", "21"],
            "wait_before": 0.0,
            "note": "AGV03 chiem N21",
        },
        {
            "agv_id": "AGV01",
            "destination": "20",
            "path": ["1", "2", "3", "18", "17", "21", "20"],
            "wait_before": 1.5,
            "note": "AGV01 di vao hanh lang N21 de toi N20",
        },
        {
            "agv_id": "AGV02",
            "destination": "23",
            "path": ["2", "3", "18", "22", "23"],
            "wait_before": 3.0,
            "note": "AGV02 chiem nhanh N23 de chan reroute cua AGV01",
        },
    ],
    "head_on_20_23": [
        # Dua AGV02 len N23 truoc, sau do AGV01 huong toi N20 de ep planner nghien cuu nhanh 20-23.
        {
            "agv_id": "AGV02",
            "destination": "23",
            "path": ["2", "3", "18", "22", "23"],
            "wait_before": 0.0,
            "note": "AGV02 len N23 truoc",
        },
        {
            "agv_id": "AGV01",
            "destination": "20",
            "path": ["1", "2", "3", "18", "22", "23", "20"],
            "wait_before": 2.0,
            "note": "AGV01 di qua nhanh 23 de toi N20",
        },
    ],
    "slowdown_merge": [
        # Hai AGV di cung hanh lang 3 -> 18 -> 22 voi do lech nho.
        # Muc tieu la de State Management khuyen nghi SLOW_DOWN thay vi hard WAIT.
        {
            "agv_id": "AGV03",
            "destination": "22",
            "path": ["3", "18", "22"],
            "wait_before": 0.0,
            "note": "AGV03 vao corridor 3-18-22 truoc",
        },
        {
            "agv_id": "AGV02",
            "destination": "23",
            "path": ["2", "3", "18", "22", "23"],
            "wait_before": 0.8,
            "note": "AGV02 bam theo cung hanh lang; mong doi predictor ra SLOW_DOWN",
        },
    ],
}


def post_move(command: dict[str, object]) -> dict[str, object]:
    body = json.dumps(command).encode("utf-8")
    request = urllib.request.Request(
        f"{SERVER_BASE_URL}/order",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def run_scenario(scenario_name: str) -> None:
    moves = SCENARIOS[scenario_name]
    started_at = time.monotonic()
    print(f"Running scenario: {scenario_name}")
    for index, move in enumerate(moves, start=1):
        wait_before = float(move.get("wait_before", 0.0))
        elapsed = time.monotonic() - started_at
        sleep_for = max(0.0, wait_before - elapsed)
        if sleep_for > 0.0:
            time.sleep(sleep_for)

        payload = {
            "agv_id": str(move["agv_id"]),
            "destination": str(move["destination"]),
        }
        if move.get("path"):
            payload["path"] = move["path"]
        if move.get("map_id"):
            payload["map_id"] = move["map_id"]

        try:
            response = post_move(payload)
            deduped = bool(response.get("deduplicated"))
            order_id = response.get("orderId")
            path = response.get("path")
            note = move.get("note") or "-"
            print(
                f"[{index}/{len(moves)}] {payload['agv_id']} -> {payload['destination']} "
                f"| orderId={order_id} | deduped={deduped} | path={path} | note={note}"
            )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            print(f"[{index}/{len(moves)}] HTTP {exc.code} for {payload['agv_id']}: {detail}")
        except Exception as exc:
            print(f"[{index}/{len(moves)}] Failed to send move for {payload['agv_id']}: {exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send controlled AGV move scenarios to /order")
    parser.add_argument(
        "--scenario",
        default="triple_conflict",
        choices=sorted(SCENARIOS.keys()),
        help="Scenario to execute",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_scenario(args.scenario)


if __name__ == "__main__":
    main()
