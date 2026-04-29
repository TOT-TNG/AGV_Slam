from __future__ import annotations

import math
from typing import Tuple

Point = Tuple[float, float]


def distance(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def distance_point_to_oriented_rect(
    point: Point,
    rect_center: Point,
    rect_theta: float,
    rect_length: float,
    rect_width: float,
) -> float:
    dx = point[0] - rect_center[0]
    dy = point[1] - rect_center[1]
    cos_t = math.cos(rect_theta)
    sin_t = math.sin(rect_theta)

    local_x = dx * cos_t + dy * sin_t
    local_y = -dx * sin_t + dy * cos_t
    outside_x = max(abs(local_x) - rect_length / 2.0, 0.0)
    outside_y = max(abs(local_y) - rect_width / 2.0, 0.0)
    return math.hypot(outside_x, outside_y)


def normalize_angle(theta: float) -> float:
    while theta > math.pi:
        theta -= 2 * math.pi
    while theta < -math.pi:
        theta += 2 * math.pi
    return theta


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def heading_to(src: Point, dst: Point) -> float:
    return math.atan2(dst[1] - src[1], dst[0] - src[0])


def project_forward(x: float, y: float, theta: float, dist: float) -> Point:
    return x + math.cos(theta) * dist, y + math.sin(theta) * dist


def point_in_polygon(point: Point, polygon: list[Point] | tuple[Point, ...]) -> bool:
    if len(polygon) < 3:
        return False
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def distance_point_to_segment(point: Point, a: Point, b: Point) -> float:
    px, py = point
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    denom = dx * dx + dy * dy
    if denom <= 1e-12:
        return distance(point, a)
    t = clamp(((px - ax) * dx + (py - ay) * dy) / denom, 0.0, 1.0)
    return math.hypot(px - (ax + dx * t), py - (ay + dy * t))


def distance_point_to_polygon(point: Point, polygon: list[Point] | tuple[Point, ...]) -> float:
    if point_in_polygon(point, polygon):
        return 0.0
    if len(polygon) < 2:
        return 999999.0
    return min(
        distance_point_to_segment(point, polygon[idx], polygon[(idx + 1) % len(polygon)])
        for idx in range(len(polygon))
    )
