from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


def ensure_generated_map(output_path: Path, graph_file: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        return

    data = json.loads(Path(graph_file).read_text(encoding='utf-8'))
    width_px = 1200
    height_px = 800
    img = Image.new('RGB', (width_px, height_px), (235, 239, 242))
    draw = ImageDraw.Draw(img)

    margin = 60
    w_m = data.get('width_m', 20.0)
    h_m = data.get('height_m', 12.0)

    def to_px(x: float, y: float) -> tuple[int, int]:
        px = int(margin + x / w_m * (width_px - 2 * margin))
        py = int(height_px - (margin + y / h_m * (height_px - 2 * margin)))
        return px, py

    # floor grid
    for i in range(0, int(w_m) + 1):
        x1, y1 = to_px(i, 0)
        x2, y2 = to_px(i, h_m)
        draw.line((x1, y1, x2, y2), fill=(215, 220, 224), width=1)
    for i in range(0, int(h_m) + 1):
        x1, y1 = to_px(0, i)
        x2, y2 = to_px(w_m, i)
        draw.line((x1, y1, x2, y2), fill=(215, 220, 224), width=1)

    node_items = data.get('node_table', data.get('nodes', []))
    line_items = data.get('line_table', data.get('edges', []))
    bezier_items = data.get('bezier_table', [])
    nodes = {n.get('node_id', n.get('id')): n for n in node_items}
    for edge in line_items:
        a = nodes[edge.get('from_node', edge.get('from'))]
        b = nodes[edge.get('to_node', edge.get('to'))]
        draw.line((*to_px(a['x'], a['y']), *to_px(b['x'], b['y'])), fill=(145, 152, 159), width=6)
    for edge in bezier_items:
        a = nodes[edge.get('from_node', edge.get('from'))]
        b = nodes[edge.get('to_node', edge.get('to'))]
        ax = float(a['x'])
        ay = float(a['y'])
        bx = float(b['x'])
        by = float(b['y'])
        if 'control1_x' in edge and 'control2_x' in edge:
            c1x = float(edge['control1_x'])
            c1y = float(edge['control1_y'])
            c2x = float(edge['control2_x'])
            c2y = float(edge['control2_y'])
        else:
            cx = float(edge.get('control_x', (ax + bx) / 2.0))
            cy = float(edge.get('control_y', (ay + by) / 2.0))
            c1x = ax + (cx - ax) * 2.0 / 3.0
            c1y = ay + (cy - ay) * 2.0 / 3.0
            c2x = bx + (cx - bx) * 2.0 / 3.0
            c2y = by + (cy - by) * 2.0 / 3.0
        points = []
        for idx in range(25):
            t = idx / 24.0
            inv = 1.0 - t
            x = inv ** 3 * ax + 3.0 * inv * inv * t * c1x + 3.0 * inv * t * t * c2x + t ** 3 * bx
            y = inv ** 3 * ay + 3.0 * inv * inv * t * c1y + 3.0 * inv * t * t * c2y + t ** 3 * by
            points.append(to_px(x, y))
        draw.line(points, fill=(145, 152, 159), width=6)
    for node in node_items:
        x, y = to_px(node['x'], node['y'])
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=(45, 92, 145), outline=(20, 50, 90), width=2)
        draw.text((x + 10, y - 16), node.get('node_id', node.get('id')), fill=(60, 60, 60))

    img.save(output_path)
