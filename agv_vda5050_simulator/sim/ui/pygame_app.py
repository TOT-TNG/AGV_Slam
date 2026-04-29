from __future__ import annotations

import math
from pathlib import Path
from typing import Callable, List, Optional

import pygame

from sim.core.agv_agent import AGVAgent
from sim.core.human_agent import HumanAgent
from sim.core.simulator import AGV_TYPES, Simulator
from sim.core.models import Velocity2D
from sim.core.state_machine import AGVMode, AGVRunState
from sim.map.graph import Edge, Graph, Node
from sim.map.loader import load_graph, load_json, save_json
from sim.map.server_payload import build_map_upload_payload, upload_map_payload
from sim.ui.widgets import Button
from sim.utils.geometry import distance


NODE_TYPES = ['intersection', 'station', 'charger', 'dock', 'elevator']


class PygameApp:
    def __init__(self, *, root: Path, config: dict, graph: Graph, simulator: Simulator) -> None:
        pygame.init()
        pygame.font.init()
        self.root = root
        self.config = config
        self.graph = graph
        self.simulator = simulator
        self.ui_cfg = config['ui']
        self.width = int(self.ui_cfg['width'])
        self.height = int(self.ui_cfg['height'])
        self.panel_width = int(self.ui_cfg['panel_width'])
        self.fps = int(self.ui_cfg['fps'])

        self.menu_height = 36
        self.map_rect = pygame.Rect(10, self.menu_height + 10, self.width - self.panel_width - 20, self.height - self.menu_height - 20)
        self.sidebar_rect = pygame.Rect(self.width - self.panel_width, 0, self.panel_width, self.height)
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption('TOT Multi-AGV simulation')
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('segoeui', 16)
        self.small_font = pygame.font.SysFont('segoeui', 14)
        self.big_font = pygame.font.SysFont('segoeui', 22, bold=True)
        self.mono_font = pygame.font.SysFont('consolas', 13)
        self._text_cache: dict[tuple[int, str, tuple[int, int, int]], pygame.Surface] = {}
        self._scaled_background_cache_key: Optional[tuple[int, int, int]] = None
        self._scaled_background_cache: Optional[pygame.Surface] = None
        self.agv_detail_render_limit = int(self.ui_cfg.get('agv_detail_render_limit', 80))
        self.safety_zone_render_limit = int(self.ui_cfg.get('safety_zone_render_limit', 80))

        self.graph_file = root / config['map']['graph_file']
        self.background_path = self._resolve_background_path(
            graph.background or config['map'].get('background'),
            graph_file=self.graph_file,
        )
        self.background = self._load_background_surface(self.background_path) if self.background_path else self._build_grid_background()
        if self.background_path and not self.graph.background:
            self.graph.background = self._path_for_map_json(self.background_path)
        self.active_layer = self.graph.layer_ids()[0] if self.graph.layer_ids() else 0
        self.active_elevator_id = self._initial_elevator_id()
        self.active_menu: Optional[str] = None
        self.active_tool_panel: Optional[str] = None
        self.camera_zoom = 1.0
        self.camera_offset = pygame.Vector2(0.0, 0.0)
        self.panning_map = False
        self.tools_scroll = 0
        self.tools_top = 456
        self.tool_button_height = 23
        self.tool_button_gap = 5
        size_cfg = config['simulation']['default_size']
        self.new_agv_form_active = False
        self.new_agv_form_fields = {
            'length': f'{float(size_cfg["length"]):.2f}',
            'width': f'{float(size_cfg["width"]):.2f}',
            'stop_distance': f'{float(config["simulation"].get("default_stop_distance", 0.9)):.2f}',
            'max_speed': '0.80',
            'max_accel': '0.50',
        }
        self.agv_form_mode = 'create'
        self.new_agv_form_type_index = 0
        self.new_agv_form_field_order = ['length', 'width', 'stop_distance', 'max_speed', 'max_accel']
        self.new_agv_form_focus = 0
        self.new_map_form_active = False
        self.new_map_form_fields = {
            'map_name': 'new_map',
            'width_m': f'{max(1.0, self.graph.width_m):.1f}',
            'height_m': f'{max(1.0, self.graph.height_m):.1f}',
        }
        self.new_map_form_field_order = ['map_name', 'width_m', 'height_m']
        self.new_map_form_focus = 0
        self.settings_form_active = False
        self.settings_form_kind = 'server'
        self.settings_form_field_order = self._settings_field_order(self.settings_form_kind)
        self.settings_form_focus = 0
        self.settings_form_fields = self._settings_fields_from_config(self.settings_form_kind)
        self.lidar_config_active = False
        self.lidar_edit_bank = 0
        self.lidar_edit_points: list[tuple[float, float]] = []
        self.lidar_drag_point_index: Optional[int] = None
        self.lidar_selected_point_index: Optional[int] = None

        self.selected_agv: Optional[AGVAgent] = None
        self.selected_human: Optional[HumanAgent] = None
        self.selected_node_id: Optional[str] = None
        self.selected_edge_id: Optional[str] = None
        self.selected_bezier_control: Optional[tuple[str, int]] = None
        self.edge_start_node_id: Optional[str] = None
        self.selected_edge_type = 'line'
        self.dragging_node_id: Optional[str] = None
        self.dragging_bezier_control: Optional[tuple[str, int]] = None
        self.dragging_agv: bool = False
        self.dragging_human: bool = False
        self.message: str = 'Ready'

        self.edit_mode: str = 'view'
        self.panel_buttons: List[Button] = []
        self._refresh_panel_buttons()

    def world_to_screen(self, x: float, y: float) -> tuple[int, int]:
        scale = self._map_scale()
        origin = self._map_origin()
        px = int(origin.x + x * scale)
        py = int(origin.y + (self.graph.height_m - y) * scale)
        return px, py

    def screen_to_world(self, x: int, y: int) -> tuple[float, float]:
        scale = self._map_scale()
        origin = self._map_origin()
        width_m = max(1.0, self.graph.width_m)
        height_m = max(1.0, self.graph.height_m)
        world_x = (x - origin.x) / scale
        world_y = height_m - ((y - origin.y) / scale)
        world_x = max(0.0, min(width_m, world_x))
        world_y = max(0.0, min(height_m, world_y))
        return world_x, world_y

    def meters_to_pixels(self, meters: float) -> float:
        return meters * self._map_scale()

    def _map_scale(self) -> float:
        width_m = max(1.0, self.graph.width_m)
        height_m = max(1.0, self.graph.height_m)
        return min(self.map_rect.width / width_m, self.map_rect.height / height_m) * self.camera_zoom

    def _map_origin(self) -> pygame.Vector2:
        scale = self._map_scale()
        world_w = self.graph.width_m * scale
        world_h = self.graph.height_m * scale
        return pygame.Vector2(
            self.map_rect.left + (self.map_rect.width - world_w) / 2.0,
            self.map_rect.top + (self.map_rect.height - world_h) / 2.0,
        ) + self.camera_offset

    def _reset_camera(self) -> None:
        self.camera_zoom = 1.0
        self.camera_offset.update(0.0, 0.0)

    def _load_background_surface(self, path: Path) -> pygame.Surface:
        try:
            return self._load_background_file(path)
        except Exception:
            return self._build_grid_background()

    def _load_background_file(self, path: Path) -> pygame.Surface:
        surface = pygame.image.load(str(path))
        if surface.get_alpha() is not None:
            return surface.convert_alpha()
        return surface.convert()

    def _resolve_background_path(self, value: Optional[str], *, graph_file: Optional[Path] = None) -> Optional[Path]:
        if not value:
            return None

        path = Path(value)
        if path.is_absolute():
            return path

        candidates = [self.root / path]
        if graph_file is not None:
            candidates.append(graph_file.parent / path)

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def _path_for_map_json(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return str(path)

    def _build_grid_background(self) -> pygame.Surface:
        surface = pygame.Surface((32, 32))
        surface.fill((235, 239, 242))
        return surface

    def _render_cached_text(
        self,
        font: pygame.font.Font,
        text: str,
        color: tuple[int, int, int],
    ) -> pygame.Surface:
        key = (id(font), text, color)
        cached = self._text_cache.get(key)
        if cached is None:
            cached = font.render(text, True, color)
            if len(self._text_cache) > 512:
                self._text_cache.clear()
            self._text_cache[key] = cached
        return cached

    def _invalidate_background_cache(self) -> None:
        self._scaled_background_cache_key = None
        self._scaled_background_cache = None

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(self.fps) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    running = self._handle_keydown(event)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._handle_mouse_down(event)
                elif event.type == pygame.MOUSEBUTTONUP:
                    self.dragging_node_id = None
                    self.dragging_bezier_control = None
                    self.lidar_drag_point_index = None
                    self.dragging_agv = False
                    self.dragging_human = False
                    self.panning_map = False
                elif event.type == pygame.MOUSEMOTION:
                    if self.lidar_config_active:
                        self._handle_lidar_config_motion(event.pos)
                    else:
                        self._handle_mouse_motion(event)
                elif event.type == pygame.MOUSEWHEEL:
                    self._handle_mouse_wheel(event)

            self.simulator.update(dt)
            self._update_manual_agv_control(dt)
            self._draw()

        self.simulator.shutdown()
        pygame.quit()

    def _handle_keydown(self, event: pygame.event.Event) -> bool:
        key = event.key
        if self.lidar_config_active:
            return self._handle_lidar_config_key(event)
        if self.settings_form_active:
            return self._handle_settings_form_key(event)
        if self.new_map_form_active:
            return self._handle_new_map_form_key(event)
        if self.new_agv_form_active:
            return self._handle_new_agv_form_key(event)

        if key == pygame.K_ESCAPE:
            self.edge_start_node_id = None
            self.dragging_node_id = None
            self.edit_mode = 'view'
            self.message = 'Switched to view mode'
            self._refresh_panel_buttons()
            return True
        if key == pygame.K_0:
            self._reset_camera()
            self.message = 'Map view reset'
        if key == pygame.K_n:
            self._set_mode('add_node')
        elif key == pygame.K_e:
            self._set_mode('add_edge')
        elif key == pygame.K_m:
            self._set_mode('move_node')
        elif key == pygame.K_d:
            self._set_mode('delete')
        elif key == pygame.K_s:
            self._save_graph()
        elif key == pygame.K_t:
            self._cycle_selected_node_type()
        elif key == pygame.K_b:
            self._toggle_selected_edge_direction()
        elif key == pygame.K_PAGEUP:
            self._select_next_layer()
        elif key == pygame.K_PAGEDOWN:
            self._select_previous_layer()
        elif key == pygame.K_DELETE:
            self._delete_selected_item()
        elif key == pygame.K_q:
            return False
        return True

    def _handle_mouse_down(self, event: pygame.event.Event) -> None:
        pos = event.pos
        if event.button == 2 and self.map_rect.collidepoint(pos):
            self.active_menu = None
            self.panning_map = True
            self.message = 'Panning map'
            return

        if event.button == 1:
            if self.lidar_config_active:
                self._handle_lidar_config_click(pos)
                return
            if self.settings_form_active:
                self._handle_settings_form_click(pos)
                return
            if self.new_map_form_active:
                self._handle_new_map_form_click(pos)
                return
            if self.new_agv_form_active:
                self._handle_new_agv_form_click(pos)
                return
            if self._handle_menu_click(pos):
                return
            if self.sidebar_rect.collidepoint(pos):
                self.active_menu = None
                self._handle_tool_button_click(pos)
                return
            if not self.map_rect.collidepoint(pos):
                self.active_menu = None
                return
            self.active_menu = None
            self._handle_map_left_click(pos)
        elif event.button == 3 and self.map_rect.collidepoint(pos):
            self.active_menu = None
            self._handle_map_right_click(pos)

    def _handle_mouse_wheel(self, event: pygame.event.Event) -> None:
        pos = pygame.mouse.get_pos()
        if self.sidebar_rect.collidepoint(pos):
            self.tools_scroll = max(0, self.tools_scroll - event.y * 28)
            return
        if self.new_map_form_active or self.new_agv_form_active or self.settings_form_active or self.lidar_config_active or not self.map_rect.collidepoint(pos):
            return

        old_zoom = self.camera_zoom
        old_origin = self._map_origin()
        factor = 1.15 ** event.y
        self.camera_zoom = max(0.25, min(8.0, self.camera_zoom * factor))
        if abs(self.camera_zoom - old_zoom) < 1e-6:
            return

        new_base_origin = self._map_origin() - self.camera_offset
        cursor = pygame.Vector2(pos)
        world_anchor = (cursor - old_origin) / self._map_scale_for_zoom(old_zoom)
        self.camera_offset = cursor - new_base_origin - world_anchor * self._map_scale()
        self.message = f'Zoom: {self.camera_zoom:.2f}x'

    def _map_scale_for_zoom(self, zoom: float) -> float:
        width_m = max(1.0, self.graph.width_m)
        height_m = max(1.0, self.graph.height_m)
        return min(self.map_rect.width / width_m, self.map_rect.height / height_m) * zoom

    def _handle_tool_button_click(self, pos: tuple[int, int]) -> None:
        clip_rect = self._tools_clip_rect()
        if not clip_rect.collidepoint(pos):
            return
        for button in self.panel_buttons:
            draw_rect = button.rect.move(self.sidebar_rect.left, self.tools_top - self.tools_scroll)
            if button.enabled and draw_rect.collidepoint(pos):
                button.callback()
                return

    def _tools_clip_rect(self) -> pygame.Rect:
        return pygame.Rect(
            self.sidebar_rect.left + 12,
            self.tools_top,
            self.panel_width - 24,
            max(0, self.height - self.tools_top - 12),
        )

    def _handle_menu_click(self, pos: tuple[int, int]) -> bool:
        for name, rect in self._menu_header_rects():
            if rect.collidepoint(pos):
                self.active_menu = None if self.active_menu == name else name
                self.active_tool_panel = name
                self._refresh_panel_buttons()
                return True

        if self.active_menu:
            for _, rect, callback in self._menu_item_rects(self.active_menu):
                if rect.collidepoint(pos):
                    self.active_tool_panel = self.active_menu
                    self.active_menu = None
                    callback()
                    self._refresh_panel_buttons()
                    return True
            if pos[1] <= self.menu_height + 180:
                self.active_menu = None
                return True

        return False

    def _menu_header_rects(self) -> list[tuple[str, pygame.Rect]]:
        x = 10
        headers = []
        for name, width in [('Map', 70), ('AGV', 70), ('Human', 86), ('Setting', 92)]:
            headers.append((name, pygame.Rect(x, 5, width, 28)))
            x += width + 4
        return headers

    def _menu_items(self, menu_name: str) -> list[tuple[str, Callable[[], None]]]:
        if menu_name == 'Map':
            return [
                ('Load map', self._load_map),
                ('New map', self._new_map),
                ('Add SLAM map', self._add_slam_map),
                ('Save map', self._save_graph),
                ('Upload map', self._upload_map_to_server),
                ('Add floor layer', self._add_floor_layer),
                ('Previous layer', self._select_previous_layer),
                ('Next layer', self._select_next_layer),
                ('Add point', lambda: self._set_mode('add_node')),
                ('New elevator id', self._new_elevator_id),
                ('Next elevator id', self._select_next_elevator),
                ('Add elevator node', lambda: self._set_mode('add_elevator_node')),
                ('Add path', lambda: self._set_mode('add_edge')),
                ('Move point/curve', lambda: self._set_mode('move_node')),
                ('Delete item', lambda: self._set_mode('delete')),
            ]
        if menu_name == 'AGV':
            return [
                ('New AGV', self._open_new_agv_form),
                ('Config AGV', self._open_config_agv_form),
                ('Config Lidar', self._open_lidar_config),
                ('Delete AGV', self._remove_selected_agv),
            ]
        if menu_name == 'Human':
            return [
                ('Add human', self._add_human),
                ('Remove human', self._remove_selected_or_last_human),
                ('Clear humans', self._clear_humans),
            ]
        if menu_name == 'Setting':
            return [
                ('Server', lambda: self._open_settings_form('server')),
                ('MQTT broker', lambda: self._open_settings_form('mqtt')),
                ('Publish rate', lambda: self._open_settings_form('publish')),
            ]
        return []

    def _menu_item_rects(self, menu_name: str) -> list[tuple[str, pygame.Rect, Callable[[], None]]]:
        header = next((rect for name, rect in self._menu_header_rects() if name == menu_name), None)
        if header is None:
            return []

        width = 160
        row_h = 30
        x = header.left
        y = header.bottom + 2
        return [
            (label, pygame.Rect(x, y + idx * row_h, width, row_h), callback)
            for idx, (label, callback) in enumerate(self._menu_items(menu_name))
        ]

    def _open_new_agv_form(self) -> None:
        self.active_tool_panel = 'AGV'
        self.new_map_form_active = False
        self.settings_form_active = False
        self.lidar_config_active = False
        self.new_agv_form_active = True
        self.agv_form_mode = 'create'
        self.new_agv_form_focus = 0
        size_cfg = self.config['simulation']['default_size']
        self.new_agv_form_fields = {
            'length': f'{float(size_cfg["length"]):.2f}',
            'width': f'{float(size_cfg["width"]):.2f}',
            'stop_distance': f'{float(self.config["simulation"].get("default_stop_distance", 0.9)):.2f}',
            'max_speed': '0.80',
            'max_accel': '0.50',
        }
        self.message = 'New AGV: enter attributes'
        self._refresh_panel_buttons()

    def _open_config_agv_form(self) -> None:
        agv = self.selected_agv
        if not agv:
            self.message = 'No AGV selected'
            return
        self.active_tool_panel = 'AGV'
        self.new_map_form_active = False
        self.settings_form_active = False
        self.lidar_config_active = False
        self.new_agv_form_active = True
        self.agv_form_mode = 'edit'
        self.new_agv_form_focus = 0
        self.new_agv_form_type_index = AGV_TYPES.index(agv.agv_type) if agv.agv_type in AGV_TYPES else 0
        self.new_agv_form_fields = {
            'length': f'{agv.size.length:.2f}',
            'width': f'{agv.size.width:.2f}',
            'stop_distance': f'{agv.stop_distance:.2f}',
            'max_speed': f'{agv.max_speed:.2f}',
            'max_accel': f'{agv.max_accel:.2f}',
        }
        self.message = f'Config {agv.agv_id}: edit attributes'
        self._refresh_panel_buttons()

    def _open_lidar_config(self) -> None:
        agv = self.selected_agv
        if not agv:
            self.message = 'No AGV selected'
            return
        self.active_tool_panel = 'AGV'
        self.new_agv_form_active = False
        self.new_map_form_active = False
        self.settings_form_active = False
        self.lidar_config_active = True
        self.lidar_edit_bank = agv.active_lidar_bank
        self.lidar_edit_points = list(agv.lidar_banks[self.lidar_edit_bank])
        self.lidar_drag_point_index = None
        self.lidar_selected_point_index = None
        self.message = f'Config lidar {agv.agv_id} bank {self.lidar_edit_bank + 1}'
        self._refresh_panel_buttons()

    def _open_new_map_form(self) -> None:
        self.active_tool_panel = 'Map'
        self.new_agv_form_active = False
        self.settings_form_active = False
        self.lidar_config_active = False
        self.new_map_form_active = True
        self.new_map_form_focus = 0
        self.new_map_form_fields = {
            'map_name': 'new_map',
            'width_m': f'{max(1.0, self.graph.width_m):.1f}',
            'height_m': f'{max(1.0, self.graph.height_m):.1f}',
        }
        self.message = 'New map: enter size'
        self._refresh_panel_buttons()

    def _open_settings_form(self, kind: str = 'server') -> None:
        self.active_tool_panel = 'Setting'
        self.new_agv_form_active = False
        self.new_map_form_active = False
        self.lidar_config_active = False
        self.settings_form_active = True
        self.settings_form_kind = kind
        self.settings_form_field_order = self._settings_field_order(kind)
        self.settings_form_focus = 0
        self.settings_form_fields = self._settings_fields_from_config(kind)
        self.message = f'Settings: edit {self._settings_title(kind).lower()}'
        self._refresh_panel_buttons()

    def _new_agv_form_rect(self) -> pygame.Rect:
        return pygame.Rect(self.map_rect.left + 40, self.map_rect.top + 40, 430, 390)

    def _new_agv_form_field_rects(self) -> dict[str, pygame.Rect]:
        form = self._new_agv_form_rect()
        return {
            key: pygame.Rect(form.left + 165, form.top + 93 + idx * 42, 120, 28)
            for idx, key in enumerate(self.new_agv_form_field_order)
        }

    def _new_agv_form_button_rects(self) -> dict[str, pygame.Rect]:
        form = self._new_agv_form_rect()
        return {
            'type': pygame.Rect(form.left + 165, form.top + 50, 155, 28),
            'create': pygame.Rect(form.left + 165, form.bottom - 52, 95, 32),
            'cancel': pygame.Rect(form.left + 270, form.bottom - 52, 95, 32),
        }

    def _new_map_form_rect(self) -> pygame.Rect:
        return pygame.Rect(self.map_rect.left + 40, self.map_rect.top + 40, 430, 270)

    def _new_map_form_field_rects(self) -> dict[str, pygame.Rect]:
        form = self._new_map_form_rect()
        return {
            key: pygame.Rect(form.left + 160, form.top + 70 + idx * 42, 170, 28)
            for idx, key in enumerate(self.new_map_form_field_order)
        }

    def _new_map_form_button_rects(self) -> dict[str, pygame.Rect]:
        form = self._new_map_form_rect()
        return {
            'create': pygame.Rect(form.left + 170, form.bottom - 52, 95, 32),
            'cancel': pygame.Rect(form.left + 275, form.bottom - 52, 95, 32),
        }

    def _settings_form_rect(self) -> pygame.Rect:
        return pygame.Rect(self.map_rect.left + 40, self.map_rect.top + 35, 650, 560)

    def _settings_form_field_rects(self) -> dict[str, pygame.Rect]:
        form = self._settings_form_rect()
        return {
            key: pygame.Rect(form.left + 190, form.top + 70 + idx * 38, 400, 27)
            for idx, key in enumerate(self.settings_form_field_order)
        }

    def _settings_form_button_rects(self) -> dict[str, pygame.Rect]:
        form = self._settings_form_rect()
        return {
            'save': pygame.Rect(form.left + 390, form.bottom - 52, 95, 32),
            'cancel': pygame.Rect(form.left + 495, form.bottom - 52, 95, 32),
        }

    def _lidar_config_rect(self) -> pygame.Rect:
        margin = 18
        max_w = max(360, self.map_rect.width - margin * 2)
        max_h = max(300, self.map_rect.height - margin * 2)
        width = min(700, max_w)
        height = min(500, max_h)
        left = self.map_rect.left + (self.map_rect.width - width) // 2
        top = self.map_rect.top + (self.map_rect.height - height) // 2
        return pygame.Rect(left, top, width, height)

    def _lidar_canvas_rect(self) -> pygame.Rect:
        form = self._lidar_config_rect()
        return pygame.Rect(form.left + 24, form.top + 58, form.width - 48, max(150, form.height - 158))

    def _lidar_config_button_rects(self) -> dict[str, pygame.Rect]:
        form = self._lidar_config_rect()
        y = form.bottom - 44
        gap = 8
        left_w = 64
        action_w = 78
        return {
            'prev': pygame.Rect(form.left + 24, y, left_w, 30),
            'next': pygame.Rect(form.left + 24 + (left_w + gap), y, left_w, 30),
            'new': pygame.Rect(form.left + 24 + 2 * (left_w + gap), y, left_w, 30),
            'clear': pygame.Rect(form.left + 24 + 3 * (left_w + gap), y, left_w, 30),
            'save': pygame.Rect(form.right - 24 - 2 * action_w - gap, y, action_w, 30),
            'cancel': pygame.Rect(form.right - 24 - action_w, y, action_w, 30),
        }

    def _handle_new_agv_form_click(self, pos: tuple[int, int]) -> None:
        buttons = self._new_agv_form_button_rects()
        if buttons['type'].collidepoint(pos):
            self.new_agv_form_type_index = (self.new_agv_form_type_index + 1) % len(AGV_TYPES)
            return
        if buttons['create'].collidepoint(pos):
            self._save_agv_form()
            return
        if buttons['cancel'].collidepoint(pos) or not self._new_agv_form_rect().collidepoint(pos):
            self.new_agv_form_active = False
            self.message = 'AGV config cancelled' if self.agv_form_mode == 'edit' else 'New AGV cancelled'
            return

        for idx, key in enumerate(self.new_agv_form_field_order):
            if self._new_agv_form_field_rects()[key].collidepoint(pos):
                self.new_agv_form_focus = idx
                return

    def _handle_lidar_config_click(self, pos: tuple[int, int]) -> None:
        agv = self.selected_agv
        if not agv:
            self.lidar_config_active = False
            return
        buttons = self._lidar_config_button_rects()
        if buttons['prev'].collidepoint(pos):
            self._load_lidar_bank(max(0, self.lidar_edit_bank - 1))
            return
        if buttons['next'].collidepoint(pos):
            self._load_lidar_bank(min(len(agv.lidar_banks) - 1, self.lidar_edit_bank + 1))
            return
        if buttons['new'].collidepoint(pos):
            agv.lidar_banks.append(list(agv.active_lidar_polygon_local()))
            self._load_lidar_bank(len(agv.lidar_banks) - 1)
            return
        if buttons['clear'].collidepoint(pos):
            self.lidar_edit_points.clear()
            self.lidar_drag_point_index = None
            self.lidar_selected_point_index = None
            return
        if buttons['save'].collidepoint(pos):
            if len(self.lidar_edit_points) < 3:
                self.message = 'Lidar polygon needs at least 3 points'
                return
            agv.set_lidar_bank(self.lidar_edit_bank, self.lidar_edit_points)
            agv.publish_state()
            self.lidar_config_active = False
            self.message = f'Saved lidar {agv.agv_id} bank {self.lidar_edit_bank + 1}'
            self._refresh_panel_buttons()
            return
        if buttons['cancel'].collidepoint(pos) or not self._lidar_config_rect().collidepoint(pos):
            self.lidar_config_active = False
            self.message = 'Lidar config cancelled'
            return

        canvas = self._lidar_canvas_rect()
        if not canvas.collidepoint(pos):
            return
        hit_idx = self._pick_lidar_point(pos)
        if hit_idx is not None:
            self.lidar_drag_point_index = hit_idx
            self.lidar_selected_point_index = hit_idx
            return
        self.lidar_edit_points.append(self._lidar_screen_to_local(pos))
        self.lidar_drag_point_index = len(self.lidar_edit_points) - 1
        self.lidar_selected_point_index = self.lidar_drag_point_index

    def _handle_lidar_config_motion(self, pos: tuple[int, int]) -> None:
        if self.lidar_drag_point_index is None:
            return
        if 0 <= self.lidar_drag_point_index < len(self.lidar_edit_points):
            self.lidar_edit_points[self.lidar_drag_point_index] = self._lidar_screen_to_local(pos)

    def _handle_lidar_config_key(self, event: pygame.event.Event) -> bool:
        if event.key == pygame.K_ESCAPE:
            self.lidar_config_active = False
            self.message = 'Lidar config cancelled'
            return True
        if event.key in {pygame.K_DELETE, pygame.K_BACKSPACE}:
            if self.lidar_selected_point_index is not None and 0 <= self.lidar_selected_point_index < len(self.lidar_edit_points):
                self.lidar_edit_points.pop(self.lidar_selected_point_index)
                self.lidar_drag_point_index = None
                self.lidar_selected_point_index = None
            return True
        return True

    def _load_lidar_bank(self, bank_index: int) -> None:
        agv = self.selected_agv
        if not agv:
            return
        self.lidar_edit_bank = bank_index
        self.lidar_edit_points = list(agv.lidar_banks[bank_index])
        self.lidar_drag_point_index = None
        self.lidar_selected_point_index = None
        self.message = f'Config lidar {agv.agv_id} bank {bank_index + 1}'

    def _pick_lidar_point(self, pos: tuple[int, int]) -> Optional[int]:
        for idx, point in enumerate(self.lidar_edit_points):
            if distance(self._lidar_local_to_screen(point), pos) <= 9:
                return idx
        return None

    def _lidar_local_to_screen(self, point: tuple[float, float]) -> tuple[int, int]:
        canvas = self._lidar_canvas_rect()
        scale = min((canvas.width - 20) / 5.0, (canvas.height - 20) / 4.0)
        origin = pygame.Vector2(canvas.left + 10 + 2.0 * scale, canvas.centery)
        return int(origin.x + point[0] * scale), int(origin.y - point[1] * scale)

    def _lidar_screen_to_local(self, pos: tuple[int, int]) -> tuple[float, float]:
        canvas = self._lidar_canvas_rect()
        scale = min((canvas.width - 20) / 5.0, (canvas.height - 20) / 4.0)
        origin = pygame.Vector2(canvas.left + 10 + 2.0 * scale, canvas.centery)
        x = (pos[0] - origin.x) / scale
        y = (origin.y - pos[1]) / scale
        return max(-2.0, min(3.0, x)), max(-1.8, min(1.8, y))

    def _handle_new_map_form_click(self, pos: tuple[int, int]) -> None:
        buttons = self._new_map_form_button_rects()
        if buttons['create'].collidepoint(pos):
            self._create_new_map_from_form()
            return
        if buttons['cancel'].collidepoint(pos) or not self._new_map_form_rect().collidepoint(pos):
            self.new_map_form_active = False
            self.message = 'New map cancelled'
            return

        field_rects = self._new_map_form_field_rects()
        for idx, key in enumerate(self.new_map_form_field_order):
            if field_rects[key].collidepoint(pos):
                self.new_map_form_focus = idx
                return

    def _handle_settings_form_click(self, pos: tuple[int, int]) -> None:
        buttons = self._settings_form_button_rects()
        if buttons['save'].collidepoint(pos):
            self._save_settings_from_form()
            return
        if buttons['cancel'].collidepoint(pos) or not self._settings_form_rect().collidepoint(pos):
            self.settings_form_active = False
            self.message = 'Settings cancelled'
            return

        field_rects = self._settings_form_field_rects()
        for idx, key in enumerate(self.settings_form_field_order):
            if field_rects[key].collidepoint(pos):
                self.settings_form_focus = idx
                return

    def _handle_new_agv_form_key(self, event: pygame.event.Event) -> bool:
        key = event.key
        if key == pygame.K_ESCAPE:
            self.new_agv_form_active = False
            self.message = 'AGV config cancelled' if self.agv_form_mode == 'edit' else 'New AGV cancelled'
            return True
        if key == pygame.K_RETURN:
            self._save_agv_form()
            return True
        if key == pygame.K_TAB:
            self.new_agv_form_focus = (self.new_agv_form_focus + 1) % len(self.new_agv_form_field_order)
            return True
        if key == pygame.K_UP:
            self.new_agv_form_type_index = (self.new_agv_form_type_index - 1) % len(AGV_TYPES)
            return True
        if key == pygame.K_DOWN:
            self.new_agv_form_type_index = (self.new_agv_form_type_index + 1) % len(AGV_TYPES)
            return True

        field = self.new_agv_form_field_order[self.new_agv_form_focus]
        value = self.new_agv_form_fields[field]
        if key == pygame.K_BACKSPACE:
            self.new_agv_form_fields[field] = value[:-1]
            return True

        char = event.unicode
        if char and (char.isdigit() or char == '.'):
            if char != '.' or '.' not in value:
                self.new_agv_form_fields[field] = value + char
        return True

    def _handle_new_map_form_key(self, event: pygame.event.Event) -> bool:
        key = event.key
        if key == pygame.K_ESCAPE:
            self.new_map_form_active = False
            self.message = 'New map cancelled'
            return True
        if key == pygame.K_RETURN:
            self._create_new_map_from_form()
            return True
        if key == pygame.K_TAB:
            self.new_map_form_focus = (self.new_map_form_focus + 1) % len(self.new_map_form_field_order)
            return True

        field = self.new_map_form_field_order[self.new_map_form_focus]
        value = self.new_map_form_fields[field]
        if key == pygame.K_BACKSPACE:
            self.new_map_form_fields[field] = value[:-1]
            return True

        char = event.unicode
        if not char:
            return True
        if field == 'map_name':
            if char.isalnum() or char in {'_', '-'}:
                self.new_map_form_fields[field] = value + char
        elif char.isdigit() or char == '.':
            if char != '.' or '.' not in value:
                self.new_map_form_fields[field] = value + char
        return True

    def _handle_settings_form_key(self, event: pygame.event.Event) -> bool:
        key = event.key
        if key == pygame.K_ESCAPE:
            self.settings_form_active = False
            self.message = 'Settings cancelled'
            return True
        if key == pygame.K_RETURN:
            self._save_settings_from_form()
            return True
        if key == pygame.K_TAB:
            self.settings_form_focus = (self.settings_form_focus + 1) % len(self.settings_form_field_order)
            return True
        if key == pygame.K_UP:
            self.settings_form_focus = (self.settings_form_focus - 1) % len(self.settings_form_field_order)
            return True
        if key == pygame.K_DOWN:
            self.settings_form_focus = (self.settings_form_focus + 1) % len(self.settings_form_field_order)
            return True

        field = self.settings_form_field_order[self.settings_form_focus]
        value = self.settings_form_fields[field]
        if key == pygame.K_BACKSPACE:
            self.settings_form_fields[field] = value[:-1]
            return True

        char = event.unicode
        if char and char.isprintable():
            self.settings_form_fields[field] = value + char
        return True

    def _update_manual_agv_control(self, dt: float) -> None:
        agv = self.selected_agv
        if not agv or agv.mode != AGVMode.MANUAL or self.new_agv_form_active or self.new_map_form_active or self.settings_form_active:
            return
        if not agv.power.power_on or agv.faults.has_error_level('FATAL'):
            return

        keys = pygame.key.get_pressed()
        move = 0.0
        rotate = 0.0
        strafe = 0.0
        if keys[pygame.K_UP]:
            move += 1.0
        if keys[pygame.K_DOWN]:
            move -= 1.0
        if keys[pygame.K_LEFT]:
            if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                strafe -= 1.0
            else:
                rotate += 1.0
        if keys[pygame.K_RIGHT]:
            if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                strafe += 1.0
            else:
                rotate -= 1.0

        turn_speed = 1.8
        manual_speed = min(0.6, agv.max_speed)
        agv.pose.theta = (agv.pose.theta + rotate * turn_speed * dt + math.pi) % (2.0 * math.pi) - math.pi

        dx = math.cos(agv.pose.theta) * move + math.sin(agv.pose.theta) * strafe
        dy = math.sin(agv.pose.theta) * move - math.cos(agv.pose.theta) * strafe
        if move or strafe:
            length = math.hypot(dx, dy)
            if length > 0:
                dx /= length
                dy /= length
            agv.pose.x = max(0.0, min(self.graph.width_m, agv.pose.x + dx * manual_speed * dt))
            agv.pose.y = max(0.0, min(self.graph.height_m, agv.pose.y + dy * manual_speed * dt))
            agv.last_node_id = self._nearest_node_id(agv.pose.x, agv.pose.y) or agv.last_node_id
            agv.velocity.linear = manual_speed * (1.0 if move >= 0 else -1.0)
            agv.run_state = AGVRunState.MOVING
            return

        agv.velocity = Velocity2D()
        if rotate:
            agv.run_state = AGVRunState.MOVING
        elif not agv.route.active:
            agv.run_state = AGVRunState.IDLE

    def _handle_mouse_motion(self, event: pygame.event.Event) -> None:
        pos = event.pos
        if self.panning_map:
            self.camera_offset.x += event.rel[0]
            self.camera_offset.y += event.rel[1]
            return

        if self.dragging_node_id and self.map_rect.collidepoint(pos):
            wx, wy = self.screen_to_world(*pos)
            self.graph.move_node(self.dragging_node_id, wx, wy)
        elif self.dragging_bezier_control and self.map_rect.collidepoint(pos):
            wx, wy = self.screen_to_world(*pos)
            edge_id, control_index = self.dragging_bezier_control
            edge = self.graph.edges.get(edge_id)
            if edge and edge.edge_type == 'bezier':
                self._set_edge_control_point(edge, control_index, wx, wy)
                self.selected_edge_id = edge.edge_id
                self.selected_bezier_control = (edge.edge_id, control_index)
        elif self.dragging_agv and self.selected_agv and self.map_rect.collidepoint(pos):
            wx, wy = self.screen_to_world(*pos)
            self.selected_agv.pose.x = wx
            self.selected_agv.pose.y = wy
            self.selected_agv.layer = self.active_layer
            self.selected_agv.last_node_id = self._nearest_node_id(wx, wy) or self.selected_agv.last_node_id
            if self.selected_agv.last_node_id in self.graph.nodes:
                node = self.graph.nodes[self.selected_agv.last_node_id]
                self.selected_agv.state_pose.x = node.x
                self.selected_agv.state_pose.y = node.y
                self.selected_agv.state_pose.theta = self.selected_agv.pose.theta
        elif self.dragging_human and self.selected_human and self.map_rect.collidepoint(pos):
            wx, wy = self.screen_to_world(*pos)
            self.selected_human.layer = self.active_layer
            self.selected_human.place(wx, wy)

    def _handle_map_left_click(self, pos: tuple[int, int]) -> None:
        wx, wy = self.screen_to_world(*pos)
        hit_control = self._pick_bezier_control(pos)
        hit_node = self._pick_node(pos)
        hit_edge = self.graph.edges.get(hit_control[0]) if hit_control else self._pick_edge(pos)
        hit_human = None if hit_control or hit_node else self._pick_human(pos)
        if hit_human:
            hit_edge = None
        hit_agv = None if hit_control or hit_node or hit_human else self._pick_agv(pos)

        self.selected_agv = None if hit_control else hit_agv
        self.selected_human = None if hit_control or hit_agv else hit_human
        if hit_agv and not hit_control:
            self.active_tool_panel = 'AGV'
        elif hit_human and not hit_control:
            self.active_tool_panel = 'Human'
        if hit_control:
            self.selected_edge_id = hit_control[0]
            self.selected_bezier_control = hit_control
            self.selected_node_id = None
        elif hit_node:
            self.selected_node_id = hit_node.node_id
            self.selected_edge_id = None
            self.selected_bezier_control = None
        elif hit_edge:
            self.selected_edge_id = hit_edge.edge_id
            self.selected_bezier_control = None
            self.selected_node_id = None
        else:
            self.selected_node_id = None
            self.selected_edge_id = None
            self.selected_bezier_control = None

        if self.edit_mode == 'add_node':
            self._add_node_at(wx, wy)
        elif self.edit_mode == 'add_elevator_node':
            self._add_node_at(wx, wy, 'elevator')
        elif self.edit_mode == 'add_edge':
            if hit_node:
                self._handle_add_edge_click(hit_node.node_id)
            else:
                self.message = 'Add edge: click 2 nodes'
        elif self.edit_mode == 'move_node':
            if hit_control:
                self.dragging_bezier_control = hit_control
                self.message = f'Moving Bezier C{hit_control[1]} {hit_control[0]}'
            elif hit_node:
                self.dragging_node_id = hit_node.node_id
                self.message = f'Moving node {hit_node.node_id}'
            elif hit_agv:
                self.dragging_agv = True
                self.message = f'Dragging AGV {hit_agv.agv_id}'
            elif hit_human:
                self.dragging_human = True
                hit_human.paused = True
                self.message = f'Dragging human {hit_human.human_id}'
        elif self.edit_mode == 'delete':
            if hit_human:
                removed = self.simulator.remove_human(hit_human.human_id)
                self.selected_human = None
                self.message = f'Removed human {removed.human_id}' if removed else 'Human already removed'
            elif hit_agv:
                removed = self.simulator.remove_agv(hit_agv.agv_id)
                self.selected_agv = None
                self.message = f'Removed AGV {removed.agv_id}' if removed else 'AGV already removed'
            elif hit_node:
                self.graph.delete_node(hit_node.node_id)
                self.selected_node_id = None
                self.selected_bezier_control = None
                self.message = f'Deleted node {hit_node.node_id}'
            elif hit_edge:
                self.graph.delete_edge(hit_edge.edge_id)
                self.selected_edge_id = None
                self.selected_bezier_control = None
                self.message = f'Deleted edge {hit_edge.edge_id}'
        else:
            if hit_control:
                self.message = f'Selected Bezier C{hit_control[1]} {hit_control[0]}'
            elif hit_human:
                self.message = f'Selected human {hit_human.human_id}'
            elif hit_agv:
                self.message = f'Selected AGV {hit_agv.agv_id}'
            elif hit_node:
                self.message = f'Selected node {hit_node.node_id}'
            elif hit_edge:
                self.message = f'Selected edge {hit_edge.edge_id}'
            else:
                self.message = 'Selection cleared'
        self._refresh_panel_buttons()

    def _handle_map_right_click(self, pos: tuple[int, int]) -> None:
        hit_node = self._pick_node(pos)
        hit_edge = self._pick_edge(pos)
        if hit_node:
            self.selected_node_id = hit_node.node_id
            self._cycle_selected_node_type()
        elif hit_edge:
            self.selected_edge_id = hit_edge.edge_id
            self._toggle_selected_edge_direction()
        self._refresh_panel_buttons()

    def _pick_node(self, pos: tuple[int, int]) -> Optional[Node]:
        for node in self._visible_nodes():
            if distance(self.world_to_screen(node.x, node.y), pos) <= 12:
                return node
        return None

    def _pick_agv(self, pos: tuple[int, int]) -> Optional[AGVAgent]:
        for agv in self.simulator.agvs:
            if agv.layer != self.active_layer:
                continue
            sx, sy = self.world_to_screen(agv.pose.x, agv.pose.y)
            half_diag = 0.5 * math.hypot(agv.size.length, agv.size.width)
            if distance((sx, sy), pos) <= self.meters_to_pixels(half_diag) + 8:
                return agv
        return None

    def _pick_human(self, pos: tuple[int, int]) -> Optional[HumanAgent]:
        for human in reversed(self.simulator.humans):
            if human.layer != self.active_layer:
                continue
            sx, sy = self.world_to_screen(human.pose.x, human.pose.y)
            radius = max(8, int(self.meters_to_pixels(human.radius)))
            if distance((sx, sy), pos) <= radius + 6:
                return human
        return None

    def _pick_edge(self, pos: tuple[int, int]) -> Optional[Edge]:
        best_edge = None
        best_dist = 999999.0
        for edge in self._visible_edges():
            d = self._point_to_polyline_distance(pos, self._edge_screen_points(edge))
            if d < 8.0 and d < best_dist:
                best_dist = d
                best_edge = edge
        return best_edge

    def _pick_bezier_control(self, pos: tuple[int, int]) -> Optional[tuple[str, int]]:
        candidates = []
        if self.selected_edge_id:
            selected = self.graph.edges.get(self.selected_edge_id)
            if selected and selected.edge_type == 'bezier':
                candidates.append(selected)
        candidates.extend(
            edge
            for edge in self._visible_edges()
            if edge.edge_type == 'bezier' and edge.edge_id != self.selected_edge_id
        )

        best_control = None
        best_dist = 999999.0
        for edge in candidates:
            threshold = 13.0 if edge.edge_id == self.selected_edge_id else 8.0
            for control_index, control_point in enumerate(self._edge_control_points(edge), start=1):
                control = self.world_to_screen(*control_point)
                d = distance(control, pos)
                if d <= threshold and d < best_dist:
                    best_dist = d
                    best_control = (edge.edge_id, control_index)
        return best_control

    def _point_to_polyline_distance(self, p: tuple[int, int], points: list[tuple[int, int]]) -> float:
        if len(points) < 2:
            return 999999.0
        return min(
            self._point_to_segment_distance(p, points[idx], points[idx + 1])
            for idx in range(len(points) - 1)
        )

    @staticmethod
    def _point_to_segment_distance(p: tuple[int, int], a: tuple[int, int], b: tuple[int, int]) -> float:
        px, py = p
        ax, ay = a
        bx, by = b
        abx = bx - ax
        aby = by - ay
        apx = px - ax
        apy = py - ay
        ab2 = abx * abx + aby * aby
        if ab2 <= 1e-9:
            return distance(p, a)
        t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab2))
        cx = ax + abx * t
        cy = ay + aby * t
        return math.hypot(px - cx, py - cy)

    def _visible_nodes(self) -> list[Node]:
        return [node for node in self.graph.nodes.values() if node.layer == self.active_layer]

    def _visible_edges(self) -> list[Edge]:
        return [
            edge
            for edge in self.graph.edges.values()
            if edge.layer == self.active_layer
            and self.graph.nodes.get(edge.from_node, Node('', 0.0, 0.0)).layer == self.active_layer
            and self.graph.nodes.get(edge.to_node, Node('', 0.0, 0.0)).layer == self.active_layer
        ]

    def _select_next_layer(self) -> None:
        layer_ids = self.graph.layer_ids()
        if not layer_ids:
            self.active_layer = 0
            return
        idx = layer_ids.index(self.active_layer) if self.active_layer in layer_ids else 0
        self._set_active_layer(layer_ids[(idx + 1) % len(layer_ids)])

    def _select_previous_layer(self) -> None:
        layer_ids = self.graph.layer_ids()
        if not layer_ids:
            self.active_layer = 0
            return
        idx = layer_ids.index(self.active_layer) if self.active_layer in layer_ids else 0
        self._set_active_layer(layer_ids[(idx - 1) % len(layer_ids)])

    def _set_active_layer(self, layer: int) -> None:
        self.active_layer = int(layer)
        self.edge_start_node_id = None
        self.selected_node_id = None
        self.selected_edge_id = None
        self.selected_bezier_control = None
        if self.selected_agv and self.selected_agv.layer != self.active_layer:
            self.selected_agv = None
        if self.selected_human and self.selected_human.layer != self.active_layer:
            self.selected_human = None
        self.message = f'Layer: {self.graph.layer_name(self.active_layer)}'
        self._refresh_panel_buttons()

    def _add_floor_layer(self) -> None:
        self.active_tool_panel = 'Map'
        layer = self.graph.next_layer_id()
        self.graph.ensure_layer(layer)
        self._set_active_layer(layer)
        self.message = f'Added layer {layer}'

    def _elevator_refs_for_node(self, node_id: str) -> list[str]:
        refs = []
        for elevator in self.simulator.elevators:
            for floor, floor_node_id in sorted(elevator.floor_nodes.items()):
                if floor_node_id == node_id:
                    refs.append(f'E{elevator.elevator_id}:F{floor}')
        return refs

    def _initial_elevator_id(self) -> int:
        if self.simulator.elevators:
            return min(elevator.elevator_id for elevator in self.simulator.elevators)
        return 1

    def _elevator_ids(self) -> list[int]:
        ids = {self.active_elevator_id}
        ids.update(elevator.elevator_id for elevator in self.simulator.elevators)
        return sorted(ids)

    def _select_next_elevator(self) -> None:
        ids = self._elevator_ids()
        idx = ids.index(self.active_elevator_id) if self.active_elevator_id in ids else 0
        self.active_elevator_id = ids[(idx + 1) % len(ids)]
        if self.selected_node_id:
            self._assign_selected_node_to_active_elevator()
        else:
            self.message = f'Active elevator = {self.active_elevator_id}'
        self._refresh_panel_buttons()

    def _new_elevator_id(self) -> None:
        self.active_tool_panel = 'Map'
        self.active_elevator_id = self.simulator.next_elevator_id()
        if self.selected_node_id:
            try:
                elevator = self.simulator.configure_elevator_floor_node(
                    node_id=self.selected_node_id,
                    elevator_id=self.active_elevator_id,
                )
            except Exception as exc:
                self.message = f'New elevator failed: {exc}'
                return
            node = self.graph.get_node(self.selected_node_id)
            self.message = f'Node {node.node_id} moved to elevator {elevator.elevator_id} floor {node.layer}'
        else:
            self.message = f'Active elevator = {self.active_elevator_id}; set floor nodes'
        self._refresh_panel_buttons()

    def _assign_selected_node_to_active_elevator(self) -> bool:
        if not self.selected_node_id:
            self.message = 'No node selected'
            return False
        try:
            elevator = self.simulator.configure_elevator_floor_node(
                node_id=self.selected_node_id,
                elevator_id=self.active_elevator_id,
            )
        except Exception as exc:
            self.message = f'Set elevator node failed: {exc}'
            return False
        node = self.graph.get_node(self.selected_node_id)
        self.message = f'Node {node.node_id} -> elevator {elevator.elevator_id} floor {node.layer}'
        return True

    def _set_mode(self, mode: str) -> None:
        self.active_tool_panel = 'Map'
        self.edit_mode = mode
        self.edge_start_node_id = None
        self.dragging_node_id = None
        self.dragging_bezier_control = None
        self.dragging_human = False
        self.message = f'Editor mode: {mode}'
        self._refresh_panel_buttons()

    def _set_new_edge_type(self, edge_type: str) -> None:
        self.active_tool_panel = 'Map'
        self.selected_edge_type = edge_type
        self.message = f'New edge type: {self.selected_edge_type}'
        self._refresh_panel_buttons()

    def _add_node_at(self, x: float, y: float, node_type: str = 'intersection') -> None:
        node_id = self.graph.next_node_id()
        self.graph.add_node(node_id, x, y, node_type, layer=self.active_layer)
        if node_type == 'elevator':
            self.simulator.configure_elevator_floor_node(node_id=node_id, elevator_id=self.active_elevator_id)
        self.selected_node_id = node_id
        self.selected_agv = None
        self.selected_human = None
        self.selected_edge_id = None
        self.selected_bezier_control = None
        suffix = f' for elevator {self.active_elevator_id}' if node_type == 'elevator' else ''
        self.message = f'Added {node_type} node {node_id} on layer {self.active_layer}{suffix}'

    def _handle_add_edge_click(self, node_id: str) -> None:
        if self.edge_start_node_id is None:
            self.edge_start_node_id = node_id
            self.message = f'Add edge: first node = {node_id}'
            return
        if self.edge_start_node_id == node_id:
            self.message = 'Add edge: choose a different second node'
            return
        try:
            edge_id = self.graph.next_edge_id()
            self.graph.add_edge(
                edge_id,
                self.edge_start_node_id,
                node_id,
                bidirectional=True,
                edge_type=self.selected_edge_type,
            )
            self.selected_edge_id = edge_id
            self.selected_bezier_control = (edge_id, 1) if self.selected_edge_type == 'bezier' else None
            self.selected_node_id = None
            self.message = f'Added {self.selected_edge_type} edge {edge_id}: {self.edge_start_node_id} -> {node_id}'
        except Exception as exc:
            self.message = f'Add edge failed: {exc}'
        finally:
            self.edge_start_node_id = None

    def _cycle_selected_node_type(self) -> None:
        if not self.selected_node_id:
            self.message = 'No node selected'
            return
        node = self.graph.get_node(self.selected_node_id)
        idx = NODE_TYPES.index(node.node_type) if node.node_type in NODE_TYPES else 0
        node.node_type = NODE_TYPES[(idx + 1) % len(NODE_TYPES)]
        if node.node_type == 'elevator':
            self.simulator.configure_elevator_floor_node(
                node_id=node.node_id,
                elevator_id=self.active_elevator_id,
            )
        self.message = f'Node {node.node_id} type = {node.node_type}'

    def _set_selected_node_elevator(self) -> None:
        self._assign_selected_node_to_active_elevator()
        self._refresh_panel_buttons()

    def _toggle_selected_edge_direction(self) -> None:
        if not self.selected_edge_id:
            self.message = 'No edge selected'
            return
        self.graph.toggle_edge_direction(self.selected_edge_id)
        edge = self.graph.edges[self.selected_edge_id]
        self.message = f'Edge {edge.edge_id} bidirectional = {edge.bidirectional}'

    def _delete_selected_item(self) -> None:
        if self.selected_node_id:
            node_id = self.selected_node_id
            self.graph.delete_node(node_id)
            self.selected_node_id = None
            self.selected_bezier_control = None
            self.message = f'Deleted node {node_id}'
        elif self.selected_edge_id:
            edge_id = self.selected_edge_id
            self.graph.delete_edge(edge_id)
            self.selected_edge_id = None
            self.selected_bezier_control = None
            self.message = f'Deleted edge {edge_id}'
        elif self.selected_human:
            human_id = self.selected_human.human_id
            removed = self.simulator.remove_human(human_id)
            self.selected_human = None
            self.message = f'Removed human {removed.human_id}' if removed else f'Human {human_id} already removed'
        elif self.selected_agv:
            agv_id = self.selected_agv.agv_id
            removed = self.simulator.remove_agv(agv_id)
            self.selected_agv = None
            self.message = f'Removed AGV {removed.agv_id}' if removed else f'AGV {agv_id} already removed'
        else:
            self.message = 'Nothing selected'
        self._refresh_panel_buttons()

    def _nearest_node_id(self, x: float, y: float) -> Optional[str]:
        best_id = None
        best_d = 999999.0
        for node in self.graph.nodes.values():
            if node.layer != self.active_layer:
                continue
            d = math.hypot(node.x - x, node.y - y)
            if d < best_d:
                best_d = d
                best_id = node.node_id
        return best_id if best_d < 1.5 else None

    def _save_graph(self) -> None:
        self.active_tool_panel = 'Map'
        data = self.graph.to_dict()
        data['agvs'] = self.simulator.snapshot_agvs()
        data['humans'] = self.simulator.snapshot_humans()
        data['elevators'] = self.simulator.snapshot_elevators()
        save_json(self.graph_file, data)
        self.config['agvs'] = data['agvs']
        self.config['humans'] = data['humans']
        self.config['elevators'] = data['elevators']
        self.message = f'Saved map + {len(data["agvs"])} AGV + {len(data["humans"])} human to {self.graph_file.name}'

    def _upload_map_to_server(self) -> None:
        self.active_tool_panel = 'Map'
        upload_cfg = self.config.get('map_upload', {})
        url = str(upload_cfg.get('url', '')).strip()
        if not url:
            self.message = 'Upload map failed: missing map_upload.url'
            return

        payload = build_map_upload_payload(
            self.graph,
            background_path=self.background_path,
            upload_config=upload_cfg,
        )
        try:
            status, response_body = upload_map_payload(
                url,
                payload,
                timeout_s=float(upload_cfg.get('timeout_s', 10)),
            )
        except Exception as exc:
            self.message = f'Upload map failed: {exc}'
            return

        if 200 <= status < 300:
            self.message = f'Uploaded map to server: HTTP {status}'
        else:
            detail = response_body.replace('\n', ' ')[:60]
            self.message = f'Upload map failed: HTTP {status} {detail}'

    @staticmethod
    def _settings_field_order(kind: str) -> list[str]:
        if kind == 'mqtt':
            return ['enabled', 'host', 'port', 'keepalive', 'interface_name', 'major_version']
        if kind == 'publish':
            return ['state_publish_hz', 'visualization_publish_hz', 'connection_publish_hz']
        return [
            'url',
            'timeout_s',
            'wrap_map_info',
            'id',
            'origin_x',
            'origin_y',
            'theta',
            'layer',
            'road_width',
            'default_speed',
        ]

    @staticmethod
    def _settings_title(kind: str) -> str:
        if kind == 'mqtt':
            return 'MQTT Broker'
        if kind == 'publish':
            return 'Publish Rate'
        return 'Server'

    def _settings_fields_from_config(self, kind: str) -> dict[str, str]:
        if kind == 'mqtt':
            mqtt_cfg = self.config.get('mqtt', {})
            return {
                'enabled': 'true' if bool(mqtt_cfg.get('enabled', True)) else 'false',
                'host': str(mqtt_cfg.get('host', '127.0.0.1')),
                'port': str(mqtt_cfg.get('port', 1883)),
                'keepalive': str(mqtt_cfg.get('keepalive', 30)),
                'interface_name': str(mqtt_cfg.get('interface_name', 'uagv')),
                'major_version': str(mqtt_cfg.get('major_version', 'v3')),
            }
        if kind == 'publish':
            sim_cfg = self.config.get('simulation', {})
            return {
                'state_publish_hz': str(sim_cfg.get('state_publish_hz', 1.0)),
                'visualization_publish_hz': str(sim_cfg.get('visualization_publish_hz', 1.0)),
                'connection_publish_hz': str(sim_cfg.get('connection_publish_hz', 0.2)),
            }

        upload_cfg = self.config.get('map_upload', {})
        return {
            'url': str(upload_cfg.get('url', '')),
            'timeout_s': str(upload_cfg.get('timeout_s', 10)),
            'wrap_map_info': 'true' if bool(upload_cfg.get('wrap_map_info', True)) else 'false',
            'id': str(upload_cfg.get('id', 0)),
            'origin_x': str(upload_cfg.get('origin_x', upload_cfg.get('x', 0.0))),
            'origin_y': str(upload_cfg.get('origin_y', upload_cfg.get('y', 0.0))),
            'theta': str(upload_cfg.get('theta', 0.0)),
            'layer': str(upload_cfg.get('layer', 0)),
            'road_width': str(upload_cfg.get('road_width', 0.95)),
            'default_speed': str(upload_cfg.get('default_speed', 0.3)),
        }

    def _save_settings_from_form(self) -> None:
        if self.settings_form_kind == 'mqtt':
            self._save_mqtt_settings_from_form()
            return
        if self.settings_form_kind == 'publish':
            self._save_publish_settings_from_form()
            return

        self._save_server_settings_from_form()

    def _save_publish_settings_from_form(self) -> None:
        try:
            parsed_cfg = {
                'state_publish_hz': self._parse_positive_float(self.settings_form_fields['state_publish_hz'], 'state publish hz'),
                'visualization_publish_hz': self._parse_positive_float(
                    self.settings_form_fields['visualization_publish_hz'],
                    'visualization publish hz',
                ),
                'connection_publish_hz': self._parse_positive_float(
                    self.settings_form_fields['connection_publish_hz'],
                    'connection publish hz',
                ),
            }
        except Exception as exc:
            self.message = f'Settings failed: {exc}'
            return

        self.simulator.update_publish_config(parsed_cfg)
        try:
            config_path = self.root / 'config' / 'simulator.json'
            data = load_json(config_path)
            sim_cfg = dict(data.get('simulation', {}))
            sim_cfg.update(parsed_cfg)
            data['simulation'] = sim_cfg
            save_json(config_path, data)
        except Exception as exc:
            self.message = f'Publish rates saved in memory only: {exc}'
            return

        self.settings_form_active = False
        self.message = 'Publish rates saved'
        self._refresh_panel_buttons()

    def _save_server_settings_from_form(self) -> None:
        try:
            parsed_cfg = {
                'url': self.settings_form_fields['url'].strip(),
                'timeout_s': self._parse_positive_float(self.settings_form_fields['timeout_s'], 'timeout'),
                'wrap_map_info': self._parse_bool(self.settings_form_fields['wrap_map_info'], 'wrap map info'),
                'id': int(self._parse_float(self.settings_form_fields['id'], 'map id')),
                'origin_x': self._parse_float(self.settings_form_fields['origin_x'], 'origin x'),
                'origin_y': self._parse_float(self.settings_form_fields['origin_y'], 'origin y'),
                'theta': self._parse_float(self.settings_form_fields['theta'], 'theta'),
                'layer': int(self._parse_float(self.settings_form_fields['layer'], 'layer')),
                'road_width': self._parse_positive_float(self.settings_form_fields['road_width'], 'road width'),
                'default_speed': self._parse_positive_float(self.settings_form_fields['default_speed'], 'default speed'),
            }
            if not parsed_cfg['url']:
                raise ValueError('server URL is required')
        except Exception as exc:
            self.message = f'Settings failed: {exc}'
            return

        upload_cfg = dict(self.config.get('map_upload', {}))
        upload_cfg.update(parsed_cfg)
        self.simulator.update_map_upload_config(upload_cfg)
        try:
            config_path = self.root / 'config' / 'simulator.json'
            data = load_json(config_path)
            data['map_upload'] = upload_cfg
            save_json(config_path, data)
        except Exception as exc:
            self.message = f'Settings saved in memory only: {exc}'
            return

        self.settings_form_active = False
        self.message = 'Server settings saved'
        self._refresh_panel_buttons()

    def _save_mqtt_settings_from_form(self) -> None:
        try:
            mqtt_cfg = {
                'enabled': self._parse_bool(self.settings_form_fields['enabled'], 'mqtt enabled'),
                'host': self.settings_form_fields['host'].strip(),
                'port': int(self._parse_positive_float(self.settings_form_fields['port'], 'mqtt port')),
                'keepalive': int(self._parse_positive_float(self.settings_form_fields['keepalive'], 'mqtt keepalive')),
                'interface_name': self.settings_form_fields['interface_name'].strip(),
                'major_version': self.settings_form_fields['major_version'].strip(),
            }
            if not mqtt_cfg['host']:
                raise ValueError('mqtt host is required')
            if not mqtt_cfg['interface_name']:
                raise ValueError('mqtt interface name is required')
            if not mqtt_cfg['major_version']:
                raise ValueError('mqtt major version is required')
        except Exception as exc:
            self.message = f'Settings failed: {exc}'
            return

        self.simulator.update_mqtt_config(mqtt_cfg)
        try:
            config_path = self.root / 'config' / 'simulator.json'
            data = load_json(config_path)
            data['mqtt'] = mqtt_cfg
            save_json(config_path, data)
        except Exception as exc:
            self.message = f'MQTT settings saved in memory only: {exc}'
            return

        self.selected_agv = None
        self.settings_form_active = False
        self.message = 'MQTT settings saved and reconnected'
        self._refresh_panel_buttons()

    def _load_map(self) -> None:
        self.active_tool_panel = 'Map'
        path = self._choose_map_file()
        if path is None:
            self.message = 'Load map cancelled'
            return

        try:
            data = load_json(path)
            graph = load_graph(path)
        except Exception as exc:
            self.message = f'Load map failed: {exc}'
            return

        agv_items = data.get('agvs') if isinstance(data.get('agvs'), list) else None
        human_items = data.get('humans') if isinstance(data.get('humans'), list) else None
        elevator_items = data.get('elevators') if isinstance(data.get('elevators'), list) else None
        self._replace_graph(graph, graph_file=path, agv_items=agv_items, human_items=human_items, elevator_items=elevator_items)
        self.message = f'Loaded map {graph.map_name}'

    def _new_map(self) -> None:
        self._open_new_map_form()

    def _add_slam_map(self) -> None:
        self.active_tool_panel = 'Map'
        path = self._choose_slam_map_file()
        if path is None:
            self.message = 'Add SLAM map cancelled'
            return

        try:
            background = self._load_background_file(path)
        except Exception as exc:
            self.message = f'Add SLAM map failed: {exc}'
            return

        self.background = background
        self.background_path = path
        self.graph.background = self._path_for_map_json(path)
        self._invalidate_background_cache()
        self.message = f'Added SLAM map {path.name}; save map to keep it'
        self._refresh_panel_buttons()

    def _create_new_map_from_form(self) -> None:
        self.active_tool_panel = 'Map'
        try:
            map_name = self._normalize_map_name(self.new_map_form_fields['map_name'])
            width_m = self._parse_positive_float(self.new_map_form_fields['width_m'], 'map width')
            height_m = self._parse_positive_float(self.new_map_form_fields['height_m'], 'map height')
        except Exception as exc:
            self.message = f'New map failed: {exc}'
            return

        graph = Graph(
            map_name=map_name,
            width_m=width_m,
            height_m=height_m,
        )
        self.new_map_form_active = False
        self._replace_graph(graph, graph_file=self._next_new_map_file())
        self._set_mode('add_node')
        self.message = f'New map {map_name}: {width_m:.1f} x {height_m:.1f} m'

    @staticmethod
    def _normalize_map_name(value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError('map name is required')
        return name

    def _replace_graph(
        self,
        graph: Graph,
        *,
        graph_file: Path,
        agv_items: Optional[list[dict]] = None,
        human_items: Optional[list[dict]] = None,
        elevator_items: Optional[list[dict]] = None,
    ) -> None:
        self.graph = graph
        self.graph_file = graph_file
        self.active_layer = graph.layer_ids()[0] if graph.layer_ids() else 0
        self.simulator.set_graph(graph)
        if agv_items is not None:
            self.simulator.replace_agvs(agv_items)
            self.config['agvs'] = self.simulator.snapshot_agvs()
        if human_items is not None:
            self.simulator.replace_humans(human_items)
            self.config['humans'] = self.simulator.snapshot_humans()
        if elevator_items is not None:
            self.simulator.replace_elevators(elevator_items)
            self.config['elevators'] = self.simulator.snapshot_elevators()
        self.active_elevator_id = self._initial_elevator_id()
        self.background_path = self._resolve_background_path(graph.background, graph_file=graph_file)
        self.background = self._load_background_surface(self.background_path) if self.background_path else self._build_grid_background()
        self._invalidate_background_cache()
        self._reset_camera()
        self.selected_agv = None
        self.selected_human = None
        self.selected_node_id = None
        self.selected_edge_id = None
        self.selected_bezier_control = None
        self.edge_start_node_id = None
        self.dragging_node_id = None
        self.dragging_bezier_control = None
        self.dragging_agv = False
        self.dragging_human = False
        self._refresh_panel_buttons()

    def _choose_map_file(self) -> Optional[Path]:
        dialog_root = None
        try:
            import tkinter as tk
            from tkinter import filedialog

            dialog_root = tk.Tk()
            dialog_root.withdraw()
            dialog_root.attributes('-topmost', True)
            file_name = filedialog.askopenfilename(
                title='Load map graph',
                initialdir=str(self.graph_file.parent),
                filetypes=[('Map graph JSON', '*.json'), ('All files', '*.*')],
            )
            return Path(file_name) if file_name else None
        except Exception:
            return self.graph_file
        finally:
            if dialog_root is not None:
                try:
                    dialog_root.destroy()
                except Exception:
                    pass

    def _choose_slam_map_file(self) -> Optional[Path]:
        dialog_root = None
        try:
            import tkinter as tk
            from tkinter import filedialog

            dialog_root = tk.Tk()
            dialog_root.withdraw()
            dialog_root.attributes('-topmost', True)
            file_name = filedialog.askopenfilename(
                title='Add SLAM map PNG',
                initialdir=str((self.root / 'assets').resolve()),
                filetypes=[('PNG image', '*.png'), ('Image files', '*.png;*.jpg;*.jpeg;*.bmp'), ('All files', '*.*')],
            )
            return Path(file_name) if file_name else None
        except Exception:
            return None
        finally:
            if dialog_root is not None:
                try:
                    dialog_root.destroy()
                except Exception:
                    pass

    def _next_new_map_file(self) -> Path:
        config_dir = self.root / 'config'
        path = config_dir / 'new_map.json'
        index = 2
        while path.exists():
            path = config_dir / f'new_map_{index}.json'
            index += 1
        return path

    def _save_agv_form(self) -> None:
        if self.agv_form_mode == 'edit':
            self._apply_agv_config()
            return
        self._add_agv()

    def _add_agv(self) -> None:
        self.active_tool_panel = 'AGV'
        try:
            length = self._parse_positive_float(self.new_agv_form_fields['length'], 'length')
            width = self._parse_positive_float(self.new_agv_form_fields['width'], 'width')
            stop_distance = self._parse_positive_float(self.new_agv_form_fields['stop_distance'], 'stop distance')
            max_speed = self._parse_positive_float(self.new_agv_form_fields['max_speed'], 'max speed')
            max_accel = self._parse_positive_float(self.new_agv_form_fields['max_accel'], 'max accel')
            agv = self.simulator.add_agv_from_form(
                agv_type=AGV_TYPES[self.new_agv_form_type_index],
                length=length,
                width=width,
                stop_distance=stop_distance,
                start_node=self.selected_node_id,
                layer=self.active_layer,
            )
        except Exception as exc:
            self.message = f'New AGV failed: {exc}'
            return
        agv.max_speed = max_speed
        agv.max_accel = max_accel
        self.new_agv_form_active = False
        self.selected_agv = agv
        self.selected_node_id = None
        self.selected_edge_id = None
        self.message = f'New {agv.agv_type} {agv.agv_id}: {agv.size.length:.2f}x{agv.size.width:.2f} m'
        self._refresh_panel_buttons()

    def _apply_agv_config(self) -> None:
        agv = self.selected_agv
        if not agv:
            self.message = 'No AGV selected'
            self.new_agv_form_active = False
            self._refresh_panel_buttons()
            return
        try:
            agv.agv_type = AGV_TYPES[self.new_agv_form_type_index]
            agv.size.length = self._parse_positive_float(self.new_agv_form_fields['length'], 'length')
            agv.size.width = self._parse_positive_float(self.new_agv_form_fields['width'], 'width')
            agv.stop_distance = self._parse_positive_float(self.new_agv_form_fields['stop_distance'], 'stop distance')
            agv.max_speed = self._parse_positive_float(self.new_agv_form_fields['max_speed'], 'max speed')
            agv.max_accel = self._parse_positive_float(self.new_agv_form_fields['max_accel'], 'max accel')
        except Exception as exc:
            self.message = f'AGV config failed: {exc}'
            return
        self.new_agv_form_active = False
        agv.publish_factsheet()
        agv.publish_state()
        self.message = f'Configured {agv.agv_id}: {agv.agv_type} {agv.size.length:.2f}x{agv.size.width:.2f} m'
        self._refresh_panel_buttons()

    @staticmethod
    def _parse_positive_float(value: str, label: str) -> float:
        parsed = float(value)
        if parsed <= 0:
            raise ValueError(f'{label} must be > 0')
        return parsed

    @staticmethod
    def _parse_float(value: str, label: str) -> float:
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError(f'{label} must be a number') from exc

    @staticmethod
    def _parse_bool(value: str, label: str) -> bool:
        normalized = value.strip().lower()
        if normalized in {'true', '1', 'yes', 'y', 'on'}:
            return True
        if normalized in {'false', '0', 'no', 'n', 'off'}:
            return False
        raise ValueError(f'{label} must be true or false')

    @staticmethod
    def _fit_text(value: str, font: pygame.font.Font, max_width: int) -> str:
        if font.size(value)[0] <= max_width:
            return value
        prefix = '...'
        trimmed = value
        while trimmed and font.size(prefix + trimmed)[0] > max_width:
            trimmed = trimmed[1:]
        return prefix + trimmed

    def _toggle_selected_agv_mode(self) -> None:
        agv = self.selected_agv
        if not agv:
            self.message = 'No AGV selected'
            return
        if agv.mode == AGVMode.AUTOMATIC:
            agv.mode = AGVMode.MANUAL
            agv.cancel_order()
            agv.velocity = Velocity2D()
            agv.run_state = AGVRunState.IDLE
        else:
            agv.mode = AGVMode.AUTOMATIC
            agv.velocity = Velocity2D()
            if not agv.route.active:
                agv.run_state = AGVRunState.IDLE
        self.message = f'{agv.agv_id} mode = {agv.mode.value}'
        agv.publish_state()
        self._refresh_panel_buttons()

    def _adjust_selected_agv_battery(self, delta: float) -> None:
        agv = self.selected_agv
        if not agv:
            self.message = 'No AGV selected'
            return
        agv.battery = max(0.0, min(100.0, agv.battery + delta))
        self.message = f'{agv.agv_id} battery = {agv.battery:.0f}%'
        agv.publish_state()
        self._refresh_panel_buttons()

    def _set_selected_agv_battery(self, value: float) -> None:
        agv = self.selected_agv
        if not agv:
            self.message = 'No AGV selected'
            return
        agv.battery = max(0.0, min(100.0, value))
        self.message = f'{agv.agv_id} battery = {agv.battery:.0f}%'
        agv.publish_state()
        self._refresh_panel_buttons()

    def _set_selected_agv_status(self, status: str) -> None:
        agv = self.selected_agv
        if not agv:
            self.message = 'No AGV selected'
            return

        if status == 'IDLE':
            agv.clear_errors()
            agv.cancel_order()
            agv.velocity = Velocity2D()
            agv.run_state = AGVRunState.IDLE
        elif status == 'PAUSED':
            agv.pause()
        elif status == 'FATAL':
            agv.inject_fatal()
            self.message = f'{agv.agv_id} state = {status}'
            self._refresh_panel_buttons()
            return
        elif status == 'FAILED':
            agv.velocity = Velocity2D()
            agv.run_state = AGVRunState.FAILED
        elif status == 'POWER_OFF':
            agv.power_off()
        elif status == 'POWER_ON':
            agv.power_on()
        else:
            self.message = f'Unsupported status: {status}'
            return
        self.message = f'{agv.agv_id} state = {status}'
        agv.publish_state()
        self._refresh_panel_buttons()

    def _toggle_selected_agv_obstacle(self) -> None:
        agv = self.selected_agv
        if not agv:
            self.message = 'No AGV selected'
            return
        agv.toggle_obstacle()
        state = 'ON' if agv.obstacle_active else 'OFF'
        self.message = f'{agv.agv_id} obstacle = {state}'
        self._refresh_panel_buttons()

    def _select_agv(self, agv: AGVAgent) -> None:
        self.active_tool_panel = 'AGV'
        self.selected_agv = agv
        self.selected_human = None
        self.selected_node_id = None
        self.selected_edge_id = None
        self.selected_bezier_control = None
        self.active_layer = agv.layer
        self.message = f'Selected AGV {agv.agv_id}'
        self._refresh_panel_buttons()

    def _remove_selected_agv(self) -> None:
        agv = self.selected_agv
        if not agv:
            self.message = 'No AGV selected'
            return
        removed = self.simulator.remove_agv(agv.agv_id)
        self.selected_agv = None
        self.message = f'Removed AGV {removed.agv_id}' if removed else f'AGV {agv.agv_id} already removed'
        self._refresh_panel_buttons()

    def _add_human(self) -> None:
        self.active_tool_panel = 'Human'
        x, y = self.screen_to_world(self.map_rect.centerx, self.map_rect.centery)
        human = self.simulator.add_human(x=x, y=y, layer=self.active_layer)
        human.pick_new_target()
        self.selected_human = human
        self.selected_agv = None
        self.message = f'Added human {human.human_id}'
        self._refresh_panel_buttons()

    def _remove_selected_or_last_human(self) -> None:
        self.active_tool_panel = 'Human'
        human_id = self.selected_human.human_id if self.selected_human else None
        removed = self.simulator.remove_human(human_id)
        if not removed:
            self.message = 'No human to remove'
            return
        if self.selected_human is removed or (human_id and self.selected_human and self.selected_human.human_id == human_id):
            self.selected_human = None
        self.message = f'Removed human {removed.human_id}'
        self._refresh_panel_buttons()

    def _clear_humans(self) -> None:
        self.active_tool_panel = 'Human'
        count = self.simulator.clear_humans()
        self.selected_human = None
        self.message = f'Cleared {count} human'
        self._refresh_panel_buttons()

    def _toggle_selected_human_paused(self) -> None:
        human = self.selected_human
        if not human:
            self.message = 'No human selected'
            return
        human.paused = not human.paused
        state = 'paused' if human.paused else 'moving'
        if not human.paused:
            human.pick_new_target()
        self.message = f'{human.human_id} {state}'
        self._refresh_panel_buttons()

    def _randomize_selected_human_target(self) -> None:
        human = self.selected_human
        if not human:
            self.message = 'No human selected'
            return
        human.paused = False
        human.pick_new_target()
        self.message = f'{human.human_id} new random target'
        self._refresh_panel_buttons()

    def _clear_selected_agv_errors(self) -> None:
        agv = self.selected_agv
        if not agv:
            self.message = 'No AGV selected'
            return
        agv.clear_errors()
        agv.publish_state()
        self.message = f'{agv.agv_id} errors cleared'
        self._refresh_panel_buttons()

    def _cancel_selected_agv_order(self) -> None:
        agv = self.selected_agv
        if not agv:
            self.message = 'No AGV selected'
            return
        agv.cancel_order()
        agv._set_action_state('ui-cancel-order', 'cancelOrder', 'FINISHED', 'Order cancelled from UI')
        agv.publish_state()
        self.message = f'{agv.agv_id} order cancelled'
        self._refresh_panel_buttons()

    def _set_selected_agv_charging(self, active: bool) -> None:
        agv = self.selected_agv
        if not agv:
            self.message = 'No AGV selected'
            return
        action_type = 'startCharging' if active else 'stopCharging'
        action_id = f'ui-{action_type}'
        agv._execute_vda_action({'actionId': action_id, 'actionType': action_type}, source='ui')
        agv.publish_state()
        state = 'ON' if active else 'OFF'
        self.message = f'{agv.agv_id} charging = {state}'
        self._refresh_panel_buttons()

    def _pick_selected_agv_load(self) -> None:
        agv = self.selected_agv
        if not agv:
            self.message = 'No AGV selected'
            return
        was_charging = agv.charging
        agv._execute_vda_action({
            'actionId': 'ui-pick',
            'actionType': 'pick',
            'actionParameters': [{'key': 'loadId', 'value': f'load-{agv.agv_id}'}],
        }, source='ui')
        agv.publish_state()
        self.message = f'{agv.agv_id} stopCharge required before pick' if was_charging else f'{agv.agv_id} picked load'
        self._refresh_panel_buttons()

    def _drop_selected_agv_load(self) -> None:
        agv = self.selected_agv
        if not agv:
            self.message = 'No AGV selected'
            return
        was_charging = agv.charging
        agv._execute_vda_action({'actionId': 'ui-drop', 'actionType': 'drop'}, source='ui')
        agv.publish_state()
        self.message = f'{agv.agv_id} stopCharge required before drop' if was_charging else f'{agv.agv_id} dropped load'
        self._refresh_panel_buttons()

    def _disconnect_selected_agv_mqtt(self) -> None:
        agv = self.selected_agv
        if not agv:
            self.message = 'No AGV selected'
            return
        agv.mqtt_disconnect()
        self.message = f'{agv.agv_id} MQTT = {self._agv_mqtt_status_label(agv)}'
        self._refresh_panel_buttons()

    def _reconnect_selected_agv_mqtt(self) -> None:
        agv = self.selected_agv
        if not agv:
            self.message = 'No AGV selected'
            return
        agv.mqtt_reconnect()
        self.message = f'{agv.agv_id} MQTT reconnecting'
        self._refresh_panel_buttons()

    def _agv_mqtt_status_label(self, agv: AGVAgent) -> str:
        if agv.mqtt_disabled_by_operator:
            return 'OPERATOR OFF'
        return agv.mqtt.status_label

    def _refresh_panel_buttons(self) -> None:
        x0 = 20
        w = self.panel_width - 40
        h = self.tool_button_height
        gap = self.tool_button_gap
        y = 0

        buttons: List[Button] = []

        if self.active_tool_panel == 'Map':
            buttons.extend([
                Button(pygame.Rect(x0, y, w, h), 'View', lambda: self._set_mode('view'), selected=self.edit_mode == 'view'),
                Button(pygame.Rect(x0, y + (h + gap), w, h), 'Add Node', lambda: self._set_mode('add_node'), selected=self.edit_mode == 'add_node'),
                Button(pygame.Rect(x0, y + 2 * (h + gap), w, h), 'Add Edge', lambda: self._set_mode('add_edge'), selected=self.edit_mode == 'add_edge'),
                Button(pygame.Rect(x0, y + 3 * (h + gap), w, h), 'Move Node/Curve', lambda: self._set_mode('move_node'), selected=self.edit_mode == 'move_node'),
                Button(pygame.Rect(x0, y + 4 * (h + gap), w, h), 'Delete', lambda: self._set_mode('delete'), selected=self.edit_mode == 'delete'),
                Button(pygame.Rect(x0, y + 5 * (h + gap), w, h), 'Add SLAM Map', self._add_slam_map),
                Button(pygame.Rect(x0, y + 6 * (h + gap), w, h), 'Save Map', self._save_graph),
                Button(pygame.Rect(x0, y + 7 * (h + gap), w, h), 'Upload Map', self._upload_map_to_server),
                Button(pygame.Rect(x0, y + 8 * (h + gap), w, h), 'Add Floor Layer', self._add_floor_layer),
                Button(pygame.Rect(x0, y + 9 * (h + gap), w, h), 'Previous Layer', self._select_previous_layer),
                Button(pygame.Rect(x0, y + 10 * (h + gap), w, h), 'Next Layer', self._select_next_layer),
                Button(pygame.Rect(x0, y + 11 * (h + gap), w, h), f'Elevator: {self.active_elevator_id}', self._select_next_elevator),
                Button(pygame.Rect(x0, y + 12 * (h + gap), w, h), 'New Elevator ID', self._new_elevator_id),
                Button(pygame.Rect(x0, y + 13 * (h + gap), w, h), 'Add Elevator Node', lambda: self._set_mode('add_elevator_node'), selected=self.edit_mode == 'add_elevator_node'),
            ])
            y += 14 * (h + gap) + 10
            buttons.extend([
                Button(pygame.Rect(x0, y, w, h), 'New Edge: Line', lambda: self._set_new_edge_type('line'), selected=self.selected_edge_type == 'line'),
                Button(pygame.Rect(x0, y + (h + gap), w, h), 'New Edge: Bezier', lambda: self._set_new_edge_type('bezier'), selected=self.selected_edge_type == 'bezier'),
                Button(pygame.Rect(x0, y + 2 * (h + gap), w, h), 'Cycle Node Type', self._cycle_selected_node_type),
                Button(pygame.Rect(x0, y + 3 * (h + gap), w, h), 'Set Node Elevator', self._set_selected_node_elevator, enabled=bool(self.selected_node_id)),
                Button(pygame.Rect(x0, y + 4 * (h + gap), w, h), 'Toggle Edge Dir', self._toggle_selected_edge_direction),
                Button(pygame.Rect(x0, y + 5 * (h + gap), w, h), 'Delete Selected', self._delete_selected_item),
            ])

        elif self.active_tool_panel == 'AGV':
            buttons.append(Button(pygame.Rect(x0, y, w, h), 'New AGV', self._open_new_agv_form))
            y += h + gap + 10

            for agv in self.simulator.agvs:
                label = f'{agv.agv_id} {agv.agv_type} L{agv.layer}'
                buttons.append(
                    Button(
                        pygame.Rect(x0, y, w, h),
                        label,
                        lambda agv=agv: self._select_agv(agv),
                        selected=self.selected_agv is agv,
                    )
                )
                y += h + gap
            if self.simulator.agvs:
                y += 10

            if self.selected_agv:
                y += 12
                agv = self.selected_agv
                agv_items = [
                    ('Config AGV', self._open_config_agv_form, False),
                    (f'Lidar Bank {agv.active_lidar_bank + 1}', self._open_lidar_config, False),
                    ('Delete AGV', self._remove_selected_agv, False),
                    (f'Mode: {agv.mode.value}', self._toggle_selected_agv_mode, agv.mode == AGVMode.MANUAL),
                    ('Battery -10%', lambda: self._adjust_selected_agv_battery(-10.0), False),
                    ('Battery +10%', lambda: self._adjust_selected_agv_battery(10.0), False),
                    ('Battery 100%', lambda: self._set_selected_agv_battery(100.0), agv.battery >= 99.9),
                    ('State: IDLE', lambda: self._set_selected_agv_status('IDLE'), agv.run_state == AGVRunState.IDLE),
                    ('State: PAUSED', lambda: self._set_selected_agv_status('PAUSED'), agv.run_state == AGVRunState.PAUSED),
                    ('State: FATAL', lambda: self._set_selected_agv_status('FATAL'), agv.run_state == AGVRunState.FAILED and agv.faults.has_error_level('FATAL')),
                    ('Toggle Obstacle', self._toggle_selected_agv_obstacle, agv.obstacle_active),
                    ('Start Charging', lambda: self._set_selected_agv_charging(True), agv.charging),
                    ('Stop Charging', lambda: self._set_selected_agv_charging(False), not agv.charging),
                    ('Pick Load', self._pick_selected_agv_load, bool(agv.loads)),
                    ('Drop Load', self._drop_selected_agv_load, not agv.loads),
                    ('MQTT Disconnect', self._disconnect_selected_agv_mqtt, agv.mqtt_disabled_by_operator or not agv.mqtt.connected),
                    ('MQTT Reconnect', self._reconnect_selected_agv_mqtt, agv.mqtt.connected and not agv.mqtt_disabled_by_operator),
                    ('Power OFF', lambda: self._set_selected_agv_status('POWER_OFF'), not agv.power.power_on),
                    ('Power ON', lambda: self._set_selected_agv_status('POWER_ON'), agv.power.power_on),
                    ('Clear Errors', self._clear_selected_agv_errors, bool(agv.faults.errors)),
                    ('Cancel Order', self._cancel_selected_agv_order, agv.route.active),
                ]
                for idx, (label, cb, selected) in enumerate(agv_items):
                    buttons.append(Button(pygame.Rect(x0, y + idx * (h + gap), w, h), label, cb, selected=selected))
        elif self.active_tool_panel == 'Human':
            buttons.extend([
                Button(pygame.Rect(x0, y, w, h), 'Add Human', self._add_human),
                Button(
                    pygame.Rect(x0, y + (h + gap), w, h),
                    'Remove Human',
                    self._remove_selected_or_last_human,
                    enabled=bool(self.simulator.humans),
                    selected=bool(self.selected_human),
                ),
                Button(
                    pygame.Rect(x0, y + 2 * (h + gap), w, h),
                    'Clear Humans',
                    self._clear_humans,
                    enabled=bool(self.simulator.humans),
                ),
            ])
            y += 3 * (h + gap) + 10
            if self.selected_human:
                human = self.selected_human
                human_items = [
                    ('Pause/Resume', self._toggle_selected_human_paused, human.paused),
                    ('New Random Target', self._randomize_selected_human_target, False),
                    ('Remove Selected', self._remove_selected_or_last_human, True),
                ]
                for idx, (label, cb, selected) in enumerate(human_items):
                    buttons.append(Button(pygame.Rect(x0, y + idx * (h + gap), w, h), label, cb, selected=selected))
        elif self.active_tool_panel == 'Setting':
            buttons.extend([
                Button(pygame.Rect(x0, y, w, h), 'Server Settings', lambda: self._open_settings_form('server'), selected=self.settings_form_kind == 'server'),
                Button(pygame.Rect(x0, y + (h + gap), w, h), 'MQTT Broker Settings', lambda: self._open_settings_form('mqtt'), selected=self.settings_form_kind == 'mqtt'),
                Button(pygame.Rect(x0, y + 2 * (h + gap), w, h), 'Publish Rate Settings', lambda: self._open_settings_form('publish'), selected=self.settings_form_kind == 'publish'),
            ])
        self.tools_scroll = min(self.tools_scroll, self._max_tools_scroll(buttons))
        self.panel_buttons = buttons

    def _max_tools_scroll(self, buttons: Optional[list[Button]] = None) -> int:
        items = buttons if buttons is not None else self.panel_buttons
        if not items:
            return 0
        content_bottom = max(button.rect.bottom for button in items)
        viewport_h = max(0, self.height - self.tools_top - 12)
        return max(0, content_bottom - viewport_h)

    def _draw(self) -> None:
        self.screen.fill((25, 28, 34))
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(self.map_rect)
        self._draw_map_background()
        self._draw_graph_overlay()
        self._draw_humans()
        self._draw_agvs()
        self.screen.set_clip(previous_clip)
        self._draw_sidebar()
        self._draw_menu_bar()
        if self.new_map_form_active:
            self._draw_new_map_form()
        if self.new_agv_form_active:
            self._draw_new_agv_form()
        if self.lidar_config_active:
            self._draw_lidar_config()
        if self.settings_form_active:
            self._draw_settings_form()
        pygame.display.flip()

    def _draw_map_background(self) -> None:
        pygame.draw.rect(self.screen, (235, 239, 242), self.map_rect)
        origin = self._map_origin()
        scale = self._map_scale()
        map_w = max(1, int(self.graph.width_m * scale))
        map_h = max(1, int(self.graph.height_m * scale))
        if self.background:
            cache_key = (id(self.background), map_w, map_h)
            if self._scaled_background_cache_key != cache_key:
                self._scaled_background_cache = pygame.transform.smoothscale(self.background, (map_w, map_h))
                self._scaled_background_cache_key = cache_key
            if self._scaled_background_cache:
                self.screen.blit(self._scaled_background_cache, (int(origin.x), int(origin.y)))
        self._draw_dynamic_grid(origin, scale)
        pygame.draw.rect(self.screen, (120, 130, 140), pygame.Rect(int(origin.x), int(origin.y), map_w, map_h), width=2)

    def _draw_dynamic_grid(self, origin: pygame.Vector2, scale: float) -> None:
        step = self._grid_step_m(scale)
        width_m = max(1.0, self.graph.width_m)
        height_m = max(1.0, self.graph.height_m)

        x = 0.0
        while x <= width_m + 1e-9:
            sx, _ = self.world_to_screen(x, 0.0)
            major = self._is_major_grid_line(x, step)
            color = (190, 198, 205) if major else (214, 220, 225)
            pygame.draw.line(self.screen, color, (sx, int(origin.y)), (sx, int(origin.y + height_m * scale)), 2 if major else 1)
            x += step

        y = 0.0
        while y <= height_m + 1e-9:
            _, sy = self.world_to_screen(0.0, y)
            major = self._is_major_grid_line(y, step)
            color = (190, 198, 205) if major else (214, 220, 225)
            pygame.draw.line(self.screen, color, (int(origin.x), sy), (int(origin.x + width_m * scale), sy), 2 if major else 1)
            y += step

    @staticmethod
    def _grid_step_m(scale: float) -> float:
        for step in [0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0]:
            if step * scale >= 32.0:
                return step
        return 100.0

    @staticmethod
    def _is_major_grid_line(value: float, step: float) -> bool:
        major_step = step * 5.0
        return abs((value / major_step) - round(value / major_step)) < 1e-6

    def _draw_menu_bar(self) -> None:
        pygame.draw.rect(self.screen, (28, 32, 38), pygame.Rect(0, 0, self.width - self.panel_width, self.menu_height))
        pygame.draw.line(
            self.screen,
            (70, 78, 88),
            (0, self.menu_height - 1),
            (self.width - self.panel_width, self.menu_height - 1),
        )

        for name, rect in self._menu_header_rects():
            active = self.active_menu == name or self.active_tool_panel == name
            color = (72, 105, 135) if active else (42, 49, 58)
            pygame.draw.rect(self.screen, color, rect, border_radius=6)
            pygame.draw.rect(self.screen, (95, 105, 118), rect, width=1, border_radius=6)
            label = self.font.render(name, True, (245, 245, 245))
            self.screen.blit(label, label.get_rect(center=rect.center))

        if not self.active_menu:
            return

        for label, rect, _ in self._menu_item_rects(self.active_menu):
            pygame.draw.rect(self.screen, (245, 247, 249), rect)
            pygame.draw.rect(self.screen, (75, 84, 96), rect, width=1)
            text = self.small_font.render(label, True, (25, 30, 36))
            self.screen.blit(text, (rect.left + 10, rect.top + 7))

    def _draw_new_agv_form(self) -> None:
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 95))
        self.screen.blit(overlay, (0, 0))

        form = self._new_agv_form_rect()
        pygame.draw.rect(self.screen, (36, 42, 50), form, border_radius=10)
        pygame.draw.rect(self.screen, (125, 145, 165), form, width=2, border_radius=10)
        title = 'Config AGV' if self.agv_form_mode == 'edit' else 'New AGV'
        self.screen.blit(self.big_font.render(title, True, (255, 255, 255)), (form.left + 22, form.top + 16))

        labels = {
            'length': 'Length (m)',
            'width': 'Width (m)',
            'stop_distance': 'Stop dist. (m)',
            'max_speed': 'Max speed (m/s)',
            'max_accel': 'Max accel (m/s2)',
        }
        buttons = self._new_agv_form_button_rects()
        self.screen.blit(self.font.render('Type', True, (225, 230, 235)), (form.left + 28, form.top + 53))
        pygame.draw.rect(self.screen, (245, 247, 249), buttons['type'], border_radius=5)
        pygame.draw.rect(self.screen, (95, 105, 118), buttons['type'], width=1, border_radius=5)
        type_text = self.font.render(AGV_TYPES[self.new_agv_form_type_index], True, (25, 30, 36))
        self.screen.blit(type_text, (buttons['type'].left + 10, buttons['type'].top + 4))

        field_rects = self._new_agv_form_field_rects()
        for idx, key in enumerate(self.new_agv_form_field_order):
            rect = field_rects[key]
            focused = idx == self.new_agv_form_focus
            self.screen.blit(self.font.render(labels[key], True, (225, 230, 235)), (form.left + 28, rect.top + 3))
            pygame.draw.rect(self.screen, (255, 255, 255), rect, border_radius=5)
            pygame.draw.rect(self.screen, (255, 210, 90) if focused else (95, 105, 118), rect, width=2 if focused else 1, border_radius=5)
            value = self.font.render(self.new_agv_form_fields[key], True, (20, 25, 30))
            self.screen.blit(value, (rect.left + 8, rect.top + 4))

        action_label = 'save' if self.agv_form_mode == 'edit' else 'create'
        hint = self.small_font.render(f'Tab: next field, Up/Down: type, Enter: {action_label}, Esc: cancel', True, (190, 205, 220))
        self.screen.blit(hint, (form.left + 24, form.bottom - 88))

        for key, label, color in [
            ('create', 'Save' if self.agv_form_mode == 'edit' else 'Create', (70, 150, 95)),
            ('cancel', 'Cancel', (125, 82, 82)),
        ]:
            rect = buttons[key]
            pygame.draw.rect(self.screen, color, rect, border_radius=7)
            pygame.draw.rect(self.screen, (25, 30, 36), rect, width=1, border_radius=7)
            text = self.small_font.render(label, True, (255, 255, 255))
            self.screen.blit(text, text.get_rect(center=rect.center))

    def _draw_lidar_config(self) -> None:
        agv = self.selected_agv
        if not agv:
            return
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 95))
        self.screen.blit(overlay, (0, 0))

        form = self._lidar_config_rect()
        canvas = self._lidar_canvas_rect()
        pygame.draw.rect(self.screen, (36, 42, 50), form, border_radius=10)
        pygame.draw.rect(self.screen, (125, 145, 165), form, width=2, border_radius=10)
        title = f'Lidar {agv.agv_id} - Bank {self.lidar_edit_bank + 1}/{len(agv.lidar_banks)}'
        self.screen.blit(self.big_font.render(title, True, (255, 255, 255)), (form.left + 22, form.top + 16))

        pygame.draw.rect(self.screen, (232, 235, 238), canvas)
        pygame.draw.rect(self.screen, (95, 105, 118), canvas, width=1)
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(canvas)
        for step in range(1, 5):
            radius = int(step * min((canvas.width - 20) / 5.0, (canvas.height - 20) / 4.0) * 0.5)
            origin = self._lidar_local_to_screen((0.0, 0.0))
            pygame.draw.circle(self.screen, (185, 190, 195), origin, radius, 1)
        for local_x in [-2, -1, 0, 1, 2, 3]:
            p1 = self._lidar_local_to_screen((float(local_x), -1.8))
            p2 = self._lidar_local_to_screen((float(local_x), 1.8))
            pygame.draw.line(self.screen, (195, 200, 205), p1, p2, 1)
        for local_y in [-1.5, -1.0, -0.5, 0, 0.5, 1.0, 1.5]:
            p1 = self._lidar_local_to_screen((-2.0, float(local_y)))
            p2 = self._lidar_local_to_screen((3.0, float(local_y)))
            pygame.draw.line(self.screen, (195, 200, 205), p1, p2, 1)

        origin = self._lidar_local_to_screen((0.0, 0.0))
        pygame.draw.line(self.screen, (35, 35, 35), self._lidar_local_to_screen((-2.0, 0.0)), self._lidar_local_to_screen((3.0, 0.0)), 2)
        pygame.draw.line(self.screen, (35, 35, 35), self._lidar_local_to_screen((0.0, -1.8)), self._lidar_local_to_screen((0.0, 1.8)), 2)
        pygame.draw.polygon(
            self.screen,
            (120, 125, 130),
            [origin, (origin[0] - 18, origin[1] + 22), (origin[0] + 18, origin[1] + 22)],
        )

        points = [self._lidar_local_to_screen(point) for point in self.lidar_edit_points]
        if len(points) >= 3:
            poly_overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            pygame.draw.polygon(poly_overlay, (90, 245, 100, 105), points)
            self.screen.blit(poly_overlay, (0, 0))
            pygame.draw.polygon(self.screen, (50, 185, 70), points, 2)
        elif len(points) >= 2:
            pygame.draw.lines(self.screen, (50, 185, 70), False, points, 2)
        for idx, point in enumerate(points):
            color = (30, 70, 220)
            if idx == self.lidar_selected_point_index:
                color = (255, 190, 40)
            pygame.draw.rect(self.screen, color, pygame.Rect(point[0] - 5, point[1] - 5, 10, 10))
        self.screen.set_clip(previous_clip)

        hint_text = 'Click add, drag edit, Delete remove'
        hint = self.small_font.render(hint_text, True, (190, 205, 220))
        hint_y = min(canvas.bottom + 10, self._lidar_config_button_rects()['prev'].top - 22)
        self.screen.blit(hint, (form.left + 24, hint_y))

        colors = {
            'prev': (78, 95, 120),
            'next': (78, 95, 120),
            'new': (70, 135, 110),
            'clear': (130, 100, 70),
            'save': (70, 150, 95),
            'cancel': (125, 82, 82),
        }
        labels = {'prev': 'Prev', 'next': 'Next', 'new': 'New', 'clear': 'Clear', 'save': 'Save', 'cancel': 'Cancel'}
        for key, rect in self._lidar_config_button_rects().items():
            enabled = not (key == 'prev' and self.lidar_edit_bank <= 0) and not (key == 'next' and self.lidar_edit_bank >= len(agv.lidar_banks) - 1)
            color = colors[key] if enabled else (75, 78, 84)
            pygame.draw.rect(self.screen, color, rect, border_radius=7)
            pygame.draw.rect(self.screen, (25, 30, 36), rect, width=1, border_radius=7)
            text = self.small_font.render(labels[key], True, (255, 255, 255))
            self.screen.blit(text, text.get_rect(center=rect.center))

    def _draw_new_map_form(self) -> None:
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 95))
        self.screen.blit(overlay, (0, 0))

        form = self._new_map_form_rect()
        pygame.draw.rect(self.screen, (36, 42, 50), form, border_radius=10)
        pygame.draw.rect(self.screen, (125, 145, 165), form, width=2, border_radius=10)
        self.screen.blit(self.big_font.render('New Map', True, (255, 255, 255)), (form.left + 22, form.top + 16))

        labels = {
            'map_name': 'Map name',
            'width_m': 'Width (m)',
            'height_m': 'Height (m)',
        }
        field_rects = self._new_map_form_field_rects()
        for idx, key in enumerate(self.new_map_form_field_order):
            rect = field_rects[key]
            focused = idx == self.new_map_form_focus
            self.screen.blit(self.font.render(labels[key], True, (225, 230, 235)), (form.left + 28, rect.top + 3))
            pygame.draw.rect(self.screen, (255, 255, 255), rect, border_radius=5)
            pygame.draw.rect(self.screen, (255, 210, 90) if focused else (95, 105, 118), rect, width=2 if focused else 1, border_radius=5)
            value = self.font.render(self.new_map_form_fields[key], True, (20, 25, 30))
            self.screen.blit(value, (rect.left + 8, rect.top + 4))

        hint = self.small_font.render('Tab: next field, Enter: create, Esc: cancel', True, (190, 205, 220))
        self.screen.blit(hint, (form.left + 24, form.bottom - 88))

        buttons = self._new_map_form_button_rects()
        for key, label, color in [
            ('create', 'Create', (70, 150, 95)),
            ('cancel', 'Cancel', (125, 82, 82)),
        ]:
            rect = buttons[key]
            pygame.draw.rect(self.screen, color, rect, border_radius=7)
            pygame.draw.rect(self.screen, (25, 30, 36), rect, width=1, border_radius=7)
            text = self.small_font.render(label, True, (255, 255, 255))
            self.screen.blit(text, text.get_rect(center=rect.center))

    def _draw_settings_form(self) -> None:
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 95))
        self.screen.blit(overlay, (0, 0))

        form = self._settings_form_rect()
        pygame.draw.rect(self.screen, (36, 42, 50), form, border_radius=10)
        pygame.draw.rect(self.screen, (125, 145, 165), form, width=2, border_radius=10)
        self.screen.blit(self.big_font.render(f'{self._settings_title(self.settings_form_kind)} Settings', True, (255, 255, 255)), (form.left + 22, form.top + 16))

        labels = {
            'url': 'Server URL',
            'timeout_s': 'Timeout (s)',
            'wrap_map_info': 'Wrap map_info',
            'id': 'Map id',
            'origin_x': 'Origin x',
            'origin_y': 'Origin y',
            'theta': 'Theta',
            'layer': 'Layer',
            'road_width': 'Road width',
            'default_speed': 'Default speed',
            'enabled': 'Enabled',
            'host': 'Broker host',
            'port': 'Broker port',
            'keepalive': 'Keepalive',
            'interface_name': 'Interface name',
            'major_version': 'Major version',
            'state_publish_hz': 'State Hz',
            'visualization_publish_hz': 'Visualization Hz',
            'connection_publish_hz': 'Connection Hz',
        }
        field_rects = self._settings_form_field_rects()
        for idx, key in enumerate(self.settings_form_field_order):
            rect = field_rects[key]
            focused = idx == self.settings_form_focus
            self.screen.blit(self.font.render(labels[key], True, (225, 230, 235)), (form.left + 28, rect.top + 3))
            pygame.draw.rect(self.screen, (255, 255, 255), rect, border_radius=5)
            pygame.draw.rect(self.screen, (255, 210, 90) if focused else (95, 105, 118), rect, width=2 if focused else 1, border_radius=5)
            value = self._fit_text(self.settings_form_fields[key], self.font, rect.width - 16)
            text = self.font.render(value, True, (20, 25, 30))
            self.screen.blit(text, (rect.left + 8, rect.top + 4))

        hint = self.small_font.render('Tab/Up/Down: field, Enter: save, Esc: cancel', True, (190, 205, 220))
        self.screen.blit(hint, (form.left + 24, form.bottom - 88))

        buttons = self._settings_form_button_rects()
        for key, label, color in [
            ('save', 'Save', (70, 150, 95)),
            ('cancel', 'Cancel', (125, 82, 82)),
        ]:
            rect = buttons[key]
            pygame.draw.rect(self.screen, color, rect, border_radius=7)
            pygame.draw.rect(self.screen, (25, 30, 36), rect, width=1, border_radius=7)
            text = self.small_font.render(label, True, (255, 255, 255))
            self.screen.blit(text, text.get_rect(center=rect.center))

    def _draw_graph_overlay(self) -> None:
        for edge in self._visible_edges():
            points = self._edge_screen_points(edge)
            color = (110, 120, 130)
            width = 3 if self.selected_edge_id == edge.edge_id else 2
            if self.selected_edge_id == edge.edge_id:
                color = (255, 210, 90)
            if len(points) >= 2:
                pygame.draw.lines(self.screen, color, False, points, width)
            if edge.edge_type == 'bezier' and self.selected_edge_id == edge.edge_id:
                c1, c2 = self._edge_control_points(edge)
                control1 = self.world_to_screen(*c1)
                control2 = self.world_to_screen(*c2)
                start = points[0]
                end = points[-1]
                pygame.draw.line(self.screen, (160, 170, 180), start, control1, 1)
                pygame.draw.line(self.screen, (160, 170, 180), control1, control2, 1)
                pygame.draw.line(self.screen, (160, 170, 180), control2, end, 1)
                for control_index, control in [(1, control1), (2, control2)]:
                    active_control = self.selected_bezier_control == (edge.edge_id, control_index)
                    pygame.draw.circle(self.screen, (255, 170, 80), control, 7 if active_control else 5)
                    pygame.draw.circle(self.screen, (35, 35, 35), control, 7 if active_control else 5, 1)
                    label = self._render_cached_text(self.mono_font, f'C{control_index}', (45, 45, 45))
                    self.screen.blit(label, (control[0] + 7, control[1] - 14))
                    if active_control:
                        pygame.draw.circle(self.screen, (255, 255, 255), control, 11, 2)
            if not edge.bidirectional:
                self._draw_edge_arrow(points)

        for node in self._visible_nodes():
            x, y = self.world_to_screen(node.x, node.y)
            color = (80, 80, 200)
            if node.node_type == 'charger':
                color = (200, 180, 0)
            elif node.node_type == 'dock':
                color = (160, 60, 180)
            elif node.node_type == 'station':
                color = (0, 140, 170)
            elif node.node_type == 'elevator':
                color = (35, 155, 95)
            radius = 9 if self.selected_node_id == node.node_id else 7
            border = (255, 255, 255) if self.selected_node_id == node.node_id else (0, 0, 0)
            pygame.draw.circle(self.screen, color, (x, y), radius)
            pygame.draw.circle(self.screen, border, (x, y), radius, 2)
            self.screen.blit(self._render_cached_text(self.mono_font, node.node_id, (35, 35, 35)), (x + 8, y - 12))
            if node.node_type == 'elevator':
                refs = self._elevator_refs_for_node(node.node_id)
                ref_label = refs[0] if refs else 'E-'
                self.screen.blit(self._render_cached_text(self.mono_font, ref_label, (20, 90, 55)), (x + 8, y + 2))

        if self.edge_start_node_id:
            node = self.graph.get_node(self.edge_start_node_id)
            x, y = self.world_to_screen(node.x, node.y)
            pygame.draw.circle(self.screen, (255, 255, 255), (x, y), 14, 2)

        self._draw_route_overlays()

    def _draw_route_overlays(self) -> None:
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        for agv in self.simulator.agvs:
            if agv.layer != self.active_layer or not agv.route.active:
                continue
            segments = self._agv_route_segments(agv)
            if not segments:
                continue
            route_color = (*agv.color, 90)
            border_color = tuple(max(0, channel - 30) for channel in agv.color)
            for points in segments:
                if len(points) < 2:
                    continue
                pygame.draw.lines(overlay, route_color, False, points, 10)
                pygame.draw.lines(self.screen, border_color, False, points, 3)
            goal_node_id = agv.route.goal_node_id
            if goal_node_id and goal_node_id in self.graph.nodes:
                goal = self.graph.get_node(goal_node_id)
                gx, gy = self.world_to_screen(goal.x, goal.y)
                pygame.draw.circle(overlay, (*agv.color, 105), (gx, gy), 14)
                pygame.draw.circle(self.screen, border_color, (gx, gy), 14, 2)
        self.screen.blit(overlay, (0, 0))

    def _agv_route_segments(self, agv: AGVAgent) -> list[list[tuple[int, int]]]:
        if not agv.route.active:
            return []
        remaining_nodes = agv.route.path_nodes[agv.route.current_index:]
        if not remaining_nodes:
            return []

        current_target = agv.route.current_target_node
        current_pose = self.world_to_screen(agv.pose.x, agv.pose.y)
        segments: list[list[tuple[int, int]]] = []
        from_node_id = agv.last_node_id

        for idx, to_node_id in enumerate(remaining_nodes):
            edge = self.graph.find_edge(from_node_id, to_node_id)
            if edge is None:
                from_node_id = to_node_id
                continue
            points = list(self._edge_screen_points(edge))
            if idx == 0 and current_target == to_node_id and points:
                points[0] = current_pose
            segments.append(points)
            from_node_id = to_node_id
        return segments

    def _edge_control_points(self, edge: Edge) -> tuple[tuple[float, float], tuple[float, float]]:
        if (
            edge.control1_x is not None
            and edge.control1_y is not None
            and edge.control2_x is not None
            and edge.control2_y is not None
        ):
            return (edge.control1_x, edge.control1_y), (edge.control2_x, edge.control2_y)
        return self.graph.default_bezier_controls(edge.from_node, edge.to_node)

    def _set_edge_control_point(self, edge: Edge, control_index: int, x: float, y: float) -> None:
        x = max(0.0, min(self.graph.width_m, x))
        y = max(0.0, min(self.graph.height_m, y))
        if control_index == 1:
            edge.control1_x = x
            edge.control1_y = y
        else:
            edge.control2_x = x
            edge.control2_y = y

    def _edge_screen_points(self, edge: Edge) -> list[tuple[int, int]]:
        a = self.graph.get_node(edge.from_node)
        b = self.graph.get_node(edge.to_node)
        if edge.edge_type != 'bezier':
            return [self.world_to_screen(a.x, a.y), self.world_to_screen(b.x, b.y)]

        (c1x, c1y), (c2x, c2y) = self._edge_control_points(edge)
        points = []
        for idx in range(25):
            t = idx / 24.0
            inv = 1.0 - t
            x = inv ** 3 * a.x + 3.0 * inv * inv * t * c1x + 3.0 * inv * t * t * c2x + t ** 3 * b.x
            y = inv ** 3 * a.y + 3.0 * inv * inv * t * c1y + 3.0 * inv * t * t * c2y + t ** 3 * b.y
            points.append(self.world_to_screen(x, y))
        return points

    def _draw_edge_arrow(self, points: list[tuple[int, int]]) -> None:
        if len(points) < 2:
            return
        mid = max(0, min(len(points) - 2, len(points) // 2))
        p1 = points[mid]
        p2 = points[mid + 1]
        angle = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
        mx = (p1[0] + p2[0]) // 2
        my = (p1[1] + p2[1]) // 2
        tip = (mx + int(math.cos(angle) * 12), my + int(math.sin(angle) * 12))
        left = (mx + int(math.cos(angle + 2.6) * 8), my + int(math.sin(angle + 2.6) * 8))
        right = (mx + int(math.cos(angle - 2.6) * 8), my + int(math.sin(angle - 2.6) * 8))
        pygame.draw.polygon(self.screen, (240, 220, 120), [tip, left, right])

    def _draw_humans(self) -> None:
        for human in self.simulator.humans:
            if human.layer != self.active_layer:
                continue
            x, y = self.world_to_screen(human.pose.x, human.pose.y)
            radius = max(7, int(self.meters_to_pixels(human.radius)))
            pygame.draw.circle(self.screen, (255, 220, 120), (x, y), radius + 5, 1)
            pygame.draw.circle(self.screen, human.color, (x, y), radius)
            pygame.draw.circle(self.screen, (45, 35, 35), (x, y), radius, 2)
            hx = x + int(math.cos(human.pose.theta) * (radius + 5))
            hy = y - int(math.sin(human.pose.theta) * (radius + 5))
            pygame.draw.line(self.screen, (45, 35, 35), (x, y), (hx, hy), 2)
            if human.paused:
                pause_label = self._render_cached_text(self.mono_font, 'P', (255, 255, 255))
                self.screen.blit(pause_label, pause_label.get_rect(center=(x, y)))
            if self.selected_human is human:
                pygame.draw.circle(self.screen, (255, 255, 255), (x, y), radius + 4, 3)
            label = self._render_cached_text(self.mono_font, human.human_id, (35, 35, 35))
            self.screen.blit(label, label.get_rect(center=(x, y - radius - 12)))

    def _draw_agvs(self) -> None:
        visible_agvs = [agv for agv in self.simulator.agvs if agv.layer == self.active_layer]
        agv_count = len(visible_agvs)
        for agv in visible_agvs:
            draw_detail = self._should_draw_agv_detail(agv, agv_count)
            x, y = self.world_to_screen(agv.pose.x, agv.pose.y)
            if draw_detail or self._agv_safety_zone_active(agv) or agv_count <= self.safety_zone_render_limit:
                self._draw_agv_safety_zone(agv)
            self._draw_agv_obstacle(agv)
            color = agv.color if agv.power.power_on else (70, 70, 70)
            polygon = self._agv_polygon(agv)
            pygame.draw.polygon(self.screen, color, polygon)
            if agv.charging:
                pygame.draw.polygon(self.screen, (70, 220, 255), polygon, width=5)
            pygame.draw.polygon(self.screen, (20, 20, 20), polygon, width=2)
            if self.selected_agv is agv:
                pygame.draw.polygon(self.screen, (255, 255, 255), polygon, width=4)

            front_len = self.meters_to_pixels(agv.size.length) * 0.55
            hx = x + int(math.cos(agv.pose.theta) * front_len)
            hy = y - int(math.sin(agv.pose.theta) * front_len)
            pygame.draw.line(self.screen, (20, 20, 20), (x, y), (hx, hy), 3)
            if draw_detail:
                label = self._render_cached_text(self.mono_font, agv.agv_id, (20, 20, 20))
                self.screen.blit(label, label.get_rect(center=(x, y - 24)))
            if agv.loads:
                load_rect = pygame.Rect(0, 0, max(12, int(self.meters_to_pixels(agv.size.width * 0.45))), max(8, int(self.meters_to_pixels(agv.size.width * 0.28))))
                load_rect.center = (x, y)
                pygame.draw.rect(self.screen, (165, 105, 45), load_rect, border_radius=2)
                pygame.draw.rect(self.screen, (70, 45, 25), load_rect, width=1, border_radius=2)
            if agv.charging and draw_detail:
                bolt = self._render_cached_text(self.mono_font, 'CHG', (20, 120, 150))
                self.screen.blit(bolt, bolt.get_rect(center=(x, y + 36)))

            if not draw_detail:
                continue
            status = agv.run_state.value
            status_color = (240, 240, 240)
            if agv.faults.has_error_level('FATAL'):
                status_color = (255, 80, 80)
            elif agv.faults.has_error_level('ERROR'):
                status_color = (255, 170, 60)
            elif agv.faults.has_error_level('WARNING'):
                status_color = (255, 235, 90)
            text = self._render_cached_text(self.mono_font, status, status_color)
            self.screen.blit(text, (x - 25, y + 20))

    def _should_draw_agv_detail(self, agv: AGVAgent, agv_count: int) -> bool:
        if agv_count <= self.agv_detail_render_limit:
            return True
        return self.selected_agv is agv or agv.faults.errors or agv.charging or bool(agv.loads)

    @staticmethod
    def _agv_safety_zone_active(agv: AGVAgent) -> bool:
        return agv.peer_stop_active or agv.human_stop_active or agv.obstacle_lidar_hit

    def _agv_polygon(self, agv: AGVAgent) -> list[tuple[int, int]]:
        cx, cy = self.world_to_screen(agv.pose.x, agv.pose.y)
        half_l = max(8.0, self.meters_to_pixels(agv.size.length) / 2.0)
        half_w = max(6.0, self.meters_to_pixels(agv.size.width) / 2.0)
        fx = math.cos(agv.pose.theta)
        fy = -math.sin(agv.pose.theta)
        rx = -fy
        ry = fx

        points = []
        for local_l, local_w in [(half_l, -half_w), (half_l, half_w), (-half_l, half_w), (-half_l, -half_w)]:
            points.append((int(cx + fx * local_l + rx * local_w), int(cy + fy * local_l + ry * local_w)))
        return points

    def _draw_agv_safety_zone(self, agv: AGVAgent) -> None:
        polygon = [self.world_to_screen(x, y) for x, y in agv.active_lidar_polygon_world()]
        if len(polygon) < 3:
            return
        active = self._agv_safety_zone_active(agv)
        color = (255, 90, 70) if active else (80, 210, 120)
        fill = (255, 90, 70, 55) if active else (80, 240, 120, 45)
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        pygame.draw.polygon(overlay, fill, polygon)
        self.screen.blit(overlay, (0, 0))
        line_width = 3 if active else 1
        pygame.draw.polygon(self.screen, color, polygon, line_width)

    def _draw_agv_obstacle(self, agv: AGVAgent) -> None:
        if not agv.obstacle_active:
            return
        ox, oy = self.world_to_screen(*agv.obstacle_point)
        radius = max(6, int(self.meters_to_pixels(0.12)))
        color = (255, 85, 70) if agv.obstacle_lidar_hit else (245, 190, 65)
        pygame.draw.circle(self.screen, color, (ox, oy), radius)
        pygame.draw.circle(self.screen, (80, 20, 20), (ox, oy), radius, 2)
        x, y = self.world_to_screen(agv.pose.x, agv.pose.y)
        sx = x + int(math.cos(agv.pose.theta) * self.meters_to_pixels(agv.size.length / 2.0))
        sy = y - int(math.sin(agv.pose.theta) * self.meters_to_pixels(agv.size.length / 2.0))
        pygame.draw.line(self.screen, (255, 120, 95), (sx, sy), (ox, oy), 2)

    def _draw_sidebar(self) -> None:
        x0 = self.sidebar_rect.left
        pygame.draw.rect(self.screen, (36, 41, 49), self.sidebar_rect)
        pygame.draw.line(self.screen, (85, 90, 100), (x0, 0), (x0, self.height), 2)
        left = x0 + 20
        right = self.width - 20
        self.screen.blit(self.big_font.render('AGV Simulator', True, (255, 255, 255)), (left, 20))

        y = 62
        mqtt_cfg = self.config['mqtt']
        visible_agvs = [agv for agv in self.simulator.agvs if agv.layer == self.active_layer]
        visible_humans = [human for human in self.simulator.humans if human.layer == self.active_layer]
        api_cfg = self.config.get('api', {})
        api_status = f'{api_cfg.get("host", "127.0.0.1")}:{api_cfg.get("port", 8088)}'
        if self.simulator.api_last_error:
            api_status = f'ERR {self.simulator.api_last_error[:18]}'
        panel = self.active_tool_panel or 'Map'
        if panel == 'Map':
            lines = [
                f'Map: {self.graph.map_name}',
                f'Layer: {self.active_layer} {self.graph.layer_name(self.active_layer)}',
                f'Active elevator: {self.active_elevator_id}',
                f'Map PNG: {self.background_path.name if self.background_path else "-"}',
                f'Graph: {len(self._visible_nodes())}/{len(self.graph.nodes)} nodes, {len(self._visible_edges())}/{len(self.graph.edges)} edges',
                f'Elevators: {len(self.simulator.elevators)} API {api_status}',
                f'Mode: {self.edit_mode}',
                f'Zoom: {self.camera_zoom:.2f}x',
                f'Status: {self.message[:30]}',
            ]
        elif panel == 'AGV':
            lines = [
                f'AGV: {len(visible_agvs)}/{len(self.simulator.agvs)} on layer',
                f'Layer: {self.active_layer} {self.graph.layer_name(self.active_layer)}',
                f'MQTT: {mqtt_cfg["host"]}:{mqtt_cfg["port"]}',
                f'VDA topic: {mqtt_cfg.get("interface_name", "uagv")}/{mqtt_cfg.get("major_version", "v3")}',
                f'Selected: {self.selected_agv.agv_id if self.selected_agv else "-"}',
                f'Status: {self.message[:30]}',
            ]
        elif panel == 'Human':
            lines = [
                f'Human: {len(visible_humans)}/{len(self.simulator.humans)} on layer',
                f'Layer: {self.active_layer} {self.graph.layer_name(self.active_layer)}',
                f'Selected: {self.selected_human.human_id if self.selected_human else "-"}',
                f'Status: {self.message[:30]}',
            ]
        elif panel == 'Setting':
            publish_cfg = self.config.get('simulation', {})
            lines = [
                f'MQTT: {mqtt_cfg["host"]}:{mqtt_cfg["port"]}',
                f'MQTT enabled: {mqtt_cfg.get("enabled", True)}',
                f'VDA topic: {mqtt_cfg.get("interface_name", "uagv")}/{mqtt_cfg.get("major_version", "v3")}',
                f'Elevator API: {api_status}',
                f'State Hz: {float(publish_cfg.get("state_publish_hz", 1.0)):.2f}',
                f'Visual Hz: {float(publish_cfg.get("visualization_publish_hz", 1.0)):.2f}',
                f'Status: {self.message[:30]}',
            ]
        else:
            lines = [
                f'Fleet: {len(visible_agvs)}/{len(self.simulator.agvs)} AGV, {len(visible_humans)}/{len(self.simulator.humans)} human',
                f'Status: {self.message[:30]}',
            ]
        for line in lines:
            self.screen.blit(self.font.render(line, True, (220, 224, 230)), (left, y))
            y += 22

        y += 12
        pygame.draw.line(self.screen, (85, 90, 100), (left, y), (right, y), 1)
        y += 14
        selection_title = {
            'Map': 'Map Selection',
            'AGV': 'AGV Selection',
            'Human': 'Human Selection',
            'Setting': 'Setting',
        }.get(panel, 'Selection')
        self.screen.blit(self.font.render(selection_title, True, (245, 245, 245)), (left, y))
        y += 28

        if panel == 'Map' and self.selected_node_id:
            node = self.graph.get_node(self.selected_node_id)
            details = [
                f'Node: {node.node_id}',
                f'Pos: ({node.x:.2f}, {node.y:.2f})',
                f'Type: {node.node_type}',
                f'Layer: {node.layer}',
            ]
            refs = self._elevator_refs_for_node(node.node_id)
            if refs:
                details.append(f'Elevator: {", ".join(refs)}')
            for line in details:
                self.screen.blit(self.font.render(line, True, (235, 238, 242)), (left, y))
                y += 20
        elif panel == 'Map' and self.selected_edge_id:
            edge = self.graph.edges[self.selected_edge_id]
            details = [
                f'Edge: {edge.edge_id}',
                f'Type: {edge.edge_type}',
                f'Path: {edge.from_node} -> {edge.to_node}',
                f'Bidirectional: {edge.bidirectional}',
                f'Layer: {edge.layer}',
            ]
            if edge.edge_type == 'bezier':
                c1, c2 = self._edge_control_points(edge)
                details.append(f'C1: ({c1[0]:.2f}, {c1[1]:.2f})')
                details.append(f'C2: ({c2[0]:.2f}, {c2[1]:.2f})')
                details.append('Adjust: Move Node/Curve + drag C1/C2')
            for line in details:
                self.screen.blit(self.font.render(line, True, (235, 238, 242)), (left, y))
                y += 20
        elif panel == 'AGV' and self.selected_agv:
            agv = self.selected_agv
            last_pub = '-'
            if agv.mqtt.last_publish_suffix:
                result = 'OK' if agv.mqtt.last_publish_ok else 'FAIL'
                last_pub = f'{agv.mqtt.last_publish_suffix} {result}'
            details = [
                f'AGV: {agv.agv_id}',
                f'Type: {agv.agv_type}',
                f'Mode: {agv.mode.value}',
                f'Power: {"ON" if agv.power.power_on else "OFF"}',
                f'MQTT: {self._agv_mqtt_status_label(agv)}',
                f'Topic: {agv.mqtt.base_topic}',
                f'Last pub: {last_pub}',
                f'Size: {agv.size.length:.2f} x {agv.size.width:.2f} m',
                f'Stop dist: {agv.stop_distance:.2f} m',
                f'Lidar bank: {agv.active_lidar_bank + 1}/{len(agv.lidar_banks)}',
                f'State: {agv.run_state.value}',
                f'Pose: ({agv.pose.x:.2f}, {agv.pose.y:.2f})',
                f'Layer: {agv.layer}',
                f'Battery: {agv.battery:.1f} %',
                f'Charging: {agv.charging} ({agv.battery_current:.1f} A)',
                f'Load: {agv.loads[0]["loadId"] if agv.loads else "-"}',
                f'Order: {agv.route.order_id or "-"}',
            ]
            if agv.obstacle_active:
                hit = 'HIT' if agv.obstacle_lidar_hit else 'clear'
                details.append(f'Obstacle: {hit} ({agv.obstacle_distance:.2f} m)')
            if agv.peer_stop_active:
                details.append(f'Peer body: {agv.peer_stop_agv_id} ({agv.peer_stop_distance:.2f} m)')
            if agv.human_stop_active:
                details.append(f'Human: {agv.human_stop_id} ({agv.human_stop_distance:.2f} m)')
            if agv.mqtt.last_error:
                details.append(f'MQTT err: {agv.mqtt.last_error[:28]}')
            for line in details:
                self.screen.blit(self.font.render(line, True, (235, 238, 242)), (left, y))
                y += 20
            if agv.mode == AGVMode.MANUAL:
                y += 4
                self.screen.blit(self.small_font.render('Manual: arrows move/turn, Shift+left/right strafe', True, (180, 195, 210)), (left, y))
                y += 18
        elif panel == 'Human' and self.selected_human:
            human = self.selected_human
            details = [
                f'Human: {human.human_id}',
                f'Pose: ({human.pose.x:.2f}, {human.pose.y:.2f})',
                f'Layer: {human.layer}',
                f'Target: ({human.target_x:.2f}, {human.target_y:.2f})',
                f'Radius: {human.radius:.2f} m',
                f'Speed: {human.speed:.2f} m/s',
                f'State: {"paused" if human.paused else "moving"}',
            ]
            for line in details:
                self.screen.blit(self.font.render(line, True, (235, 238, 242)), (left, y))
                y += 20
        elif panel == 'Setting':
            details = [
                f'Broker: {mqtt_cfg["host"]}:{mqtt_cfg["port"]}',
                f'Keepalive: {mqtt_cfg["keepalive"]} s',
                f'Namespace: {mqtt_cfg.get("interface_name", "uagv")}',
                f'Version: {mqtt_cfg.get("major_version", "v3")}',
                f'API: {api_status}',
            ]
            for line in details:
                self.screen.blit(self.font.render(line, True, (235, 238, 242)), (left, y))
                y += 20
        else:
            self.screen.blit(self.font.render('None', True, (175, 185, 196)), (left, y))

        self.tools_top = min(max(y + 18, 330), self.height - 170)
        self.tools_scroll = min(self.tools_scroll, self._max_tools_scroll())
        tool_label = self.active_tool_panel if self.active_tool_panel else 'Select Map, AGV or Human'
        pygame.draw.line(self.screen, (85, 90, 100), (left, self.tools_top - 30), (right, self.tools_top - 30), 1)
        self.screen.blit(self.font.render(f'Tools: {tool_label}', True, (245, 245, 245)), (left, self.tools_top - 22))
        if self.active_tool_panel is None:
            self.screen.blit(
                self.small_font.render('Choose Map, AGV or Human from the menu.', True, (180, 195, 210)),
                (left, self.tools_top + 4),
            )

        clip_rect = self._tools_clip_rect()
        pygame.draw.rect(self.screen, (31, 36, 44), clip_rect)
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(clip_rect)
        for btn in self.panel_buttons:
            draw_rect = btn.rect.move(self.sidebar_rect.left, self.tools_top - self.tools_scroll)
            if draw_rect.bottom >= clip_rect.top and draw_rect.top <= clip_rect.bottom:
                btn.draw(self.screen, self.small_font, rect=draw_rect)
        self.screen.set_clip(previous_clip)

        max_scroll = self._max_tools_scroll()
        if max_scroll > 0:
            track = pygame.Rect(right - 6, clip_rect.top, 4, clip_rect.height)
            thumb_h = max(24, int(clip_rect.height * clip_rect.height / (clip_rect.height + max_scroll)))
            thumb_y = clip_rect.top + int((clip_rect.height - thumb_h) * self.tools_scroll / max_scroll)
            pygame.draw.rect(self.screen, (70, 78, 88), track, border_radius=2)
            pygame.draw.rect(self.screen, (130, 150, 170), pygame.Rect(track.left, thumb_y, track.width, thumb_h), border_radius=2)
