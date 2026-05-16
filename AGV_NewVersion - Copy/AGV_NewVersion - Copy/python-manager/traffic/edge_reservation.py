"""
traffic/edge_reservation.py — Edge-level reservation for head-on prevention
---------------------------------------------------------------------------
Track which physical edges are currently being traversed.

Lifecycle:
  reserve(agv_id, from_tag, to_tag)   → called when AGV departs from a node
  release(agv_id, from_tag, to_tag)   → called when AGV arrives at next node
  release_all(agv_id)                 → called when AGV finishes/cancels trip
  is_blocked(from_t, to_t, agv_id)    → True if reverse direction is reserved

Head-on prevention:
  If AGV A reserves edge 5→6, any other AGV wanting to enter 6→5 gets blocked.
"""
from __future__ import annotations
import time


class EdgeReservationManager:
    """Track edge occupancy to prevent head-on collisions."""

    def __init__(self):
        # (from_tag, to_tag) → agv_id
        self._reserved: dict[tuple, str] = {}
        # agv_id → set of (from_tag, to_tag) reserved by this AGV
        self._agv_edges: dict[str, set] = {}

    # ── Reserve ───────────────────────────────────────────────────────────────
    def reserve(self, agv_id: str, from_tag: int, to_tag: int) -> None:
        """AGV is about to traverse edge from_tag→to_tag."""
        key = (int(from_tag), int(to_tag))
        old_owner = self._reserved.get(key)
        if old_owner and old_owner != agv_id:
            print(f"[EDGE_RES] WARN: overwriting {key} from {old_owner} → {agv_id}")
        self._reserved[key] = agv_id
        self._agv_edges.setdefault(agv_id, set()).add(key)

    # ── Release ───────────────────────────────────────────────────────────────
    def release(self, agv_id: str, from_tag: int, to_tag: int) -> None:
        """AGV finished traversing edge from_tag→to_tag."""
        key = (int(from_tag), int(to_tag))
        if self._reserved.get(key) == agv_id:
            del self._reserved[key]
            self._agv_edges.get(agv_id, set()).discard(key)

    def release_all(self, agv_id: str) -> None:
        """Release all edges held by agv_id (trip cancel / finish)."""
        edges = list(self._agv_edges.pop(agv_id, set()))
        for key in edges:
            if self._reserved.get(key) == agv_id:
                del self._reserved[key]
        if edges:
            print(f"[EDGE_RES] {agv_id}: released all {len(edges)} edge(s)")

    # ── Conflict check ────────────────────────────────────────────────────────
    def is_blocked(self, from_tag: int, to_tag: int,
                   requesting_agv: str = "") -> tuple[bool, str]:
        """
        Return (True, owner_id) if entering from_tag→to_tag would cause head-on.
        Checks whether the REVERSE direction (to_tag→from_tag) is already reserved
        by a DIFFERENT AGV.
        """
        reverse_key = (int(to_tag), int(from_tag))
        owner = self._reserved.get(reverse_key)
        if owner and owner != requesting_agv:
            return True, owner
        return False, ""

    def is_same_dir_blocked(self, from_tag: int, to_tag: int,
                             requesting_agv: str = "") -> tuple[bool, str]:
        """
        Return (True, owner_id) if the SAME direction edge is already reserved
        by another AGV (two AGVs trying to enter the same one-lane edge).
        """
        key = (int(from_tag), int(to_tag))
        owner = self._reserved.get(key)
        if owner and owner != requesting_agv:
            return True, owner
        return False, ""

    # ── Status ────────────────────────────────────────────────────────────────
    def get_status(self) -> dict:
        return {f"{k[0]}→{k[1]}": v for k, v in self._reserved.items()}

    def print_status(self) -> None:
        if not self._reserved:
            print("[EDGE_RES] No edges reserved.")
            return
        print("[EDGE_RES] Reserved edges:")
        for (fr, to), agv in self._reserved.items():
            print(f"  {fr}→{to} : {agv}")
