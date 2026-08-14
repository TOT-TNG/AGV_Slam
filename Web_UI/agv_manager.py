from dash import html, dcc
import dash_bootstrap_components as dbc
from dash import callback, Output, Input, State, ALL, no_update
import dash
import os
import datetime
import threading
from i18n import t

try:
    import psycopg2
except ImportError:
    psycopg2 = None

STATUS_THRESHOLD_SECONDS = 30
_SCHEMA_INIT_LOCK_KEY = 4213379001
_schema_lock = threading.Lock()
_schema_ready = False


def _db_conn():
    """Create a PostgreSQL connection from environment variables."""
    if not psycopg2:
        print("[WARN] psycopg2 not installed; DB operations are disabled.")
        return None
    cfg = {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": os.environ.get("PGPORT", "5432"),
        "user": os.environ.get("PGUSER", "postgres"),
        "password": os.environ.get("PGPASSWORD", "ducmanh1801"),
        "dbname": os.environ.get("PGDATABASE", "TOT_AGV"),
    }
    try:
        return psycopg2.connect(**cfg)
    except Exception as exc:
        print(f"[ERROR] Cannot connect to PostgreSQL: {exc}")
        return None


def _ensure_table():
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
    conn = _db_conn()
    if not conn:
        return
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s);", (_SCHEMA_INIT_LOCK_KEY,))
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS agv_devices (
                    name        TEXT PRIMARY KEY,
                    agv_type    TEXT NOT NULL,
                    ip          INET,
                    port        INTEGER,
                    map_id      TEXT,
                    last_seen   TIMESTAMPTZ,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                """
            )
            cur.execute("ALTER TABLE agv_devices ADD COLUMN IF NOT EXISTS map_id TEXT;")
            cur.execute("ALTER TABLE agv_devices ADD COLUMN IF NOT EXISTS factory TEXT;")
            # Khả năng lùi (MỚI — cho xe đầu kéo/rơ-moóc chỉ đi 1 chiều tiến).
            # DEFAULT TRUE → mọi AGV hiện có (carry) giữ nguyên hành vi cũ.
            cur.execute("ALTER TABLE agv_devices ADD COLUMN IF NOT EXISTS can_reverse BOOLEAN DEFAULT TRUE;")
            cur.execute(
                """
                CREATE OR REPLACE FUNCTION set_updated_at()
                RETURNS TRIGGER AS $$
                BEGIN
                  NEW.updated_at = now();
                  RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                """
            )
            cur.execute(
                """
                DO $$
                BEGIN
                  IF NOT EXISTS (
                    SELECT 1
                    FROM pg_trigger
                    WHERE tgname = 'trg_agv_devices_updated'
                      AND tgrelid = 'agv_devices'::regclass
                  ) THEN
                    CREATE TRIGGER trg_agv_devices_updated
                    BEFORE UPDATE ON agv_devices
                    FOR EACH ROW
                    EXECUTE FUNCTION set_updated_at();
                  END IF;
                END
                $$;
                """
            )
            cur.execute("SELECT pg_advisory_unlock(%s);", (_SCHEMA_INIT_LOCK_KEY,))
        _schema_ready = True
    finally:
        conn.close()


def _icon_for_type(agv_type: str):
    icon_map = {
        "slam_qr": "/assets/agv_slam_icon.png",
        "carry": "/assets/AGV_cho_icon.png",
        "tow": "/assets/AGV_keo_icon.png",
        "trailer": "/assets/AGV_romoc_icon.png",
    }
    return icon_map.get((agv_type or "").lower(), "/assets/agv_slam_icon.png")


def _status_from_last_seen(last_seen):
    if not last_seen:
        return "Offline"
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    delta = (now_utc - last_seen).total_seconds()
    return "Online" if delta <= STATUS_THRESHOLD_SECONDS else "Offline"


def load_maps():
    """Fetch map list from agv_maps table for dropdown."""
    conn = _db_conn()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM agv_maps ORDER BY modify_time DESC NULLS LAST")
            rows = cur.fetchall()
        return [{"id": str(r[0]), "name": r[1] or f"Map {r[0]}"} for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def load_factories():
    """Danh sách nhà máy (factory) DUY NHẤT đã có trong agv_devices — gợi ý khi
    thêm AGV mới, để các xe cùng 1 nhà máy tự nhiên dùng chung 1 giá trị factory
    (namespace topic MQTT), không phải gõ tay lặp lại dễ gõ lệch chính tả."""
    conn = _db_conn()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT factory FROM agv_devices "
                "WHERE factory IS NOT NULL AND factory <> '' ORDER BY factory"
            )
            rows = cur.fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def load_agvs():
    """Fetch AGV list from DB; fallback to empty list if DB unavailable."""
    _ensure_table()
    conn = _db_conn()
    if not conn:
        return []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name, agv_type, CAST(ip AS TEXT), port, map_id, factory, last_seen, "
            "COALESCE(can_reverse, TRUE) "
            "FROM agv_devices ORDER BY name"
        )
        rows = cur.fetchall()
    conn.close()
    result = []
    for name, agv_type, ip, port, map_id, factory, last_seen, can_reverse in rows:
        result.append(
            {
                "name":        name,
                "ip":          ip or "",
                "port":        str(port) if port else "",
                "map_id":      map_id or "",
                "factory":     factory or "",
                "status":      _status_from_last_seen(last_seen),
                "icon":        _icon_for_type(agv_type),
                "agv_type":    agv_type or "",
                "can_reverse": bool(can_reverse),
            }
        )
    return result


def upsert_agv(name, agv_type, ip, port, map_id=None, factory=None, can_reverse=True):
    """Insert/update AGV without touching last_seen (stays NULL until real heartbeat).
    can_reverse mặc định True (carry) — xe đầu kéo/rơ-moóc (chỉ tiến) truyền False."""
    _ensure_table()
    conn = _db_conn()
    if not conn:
        return
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agv_devices (name, agv_type, ip, port, map_id, factory, can_reverse, last_seen)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)
            ON CONFLICT (name) DO UPDATE
              SET agv_type    = EXCLUDED.agv_type,
                  ip          = EXCLUDED.ip,
                  port        = EXCLUDED.port,
                  map_id      = EXCLUDED.map_id,
                  factory     = EXCLUDED.factory,
                  can_reverse = EXCLUDED.can_reverse
            """,
            (name, agv_type or "trailer", ip, port, map_id or None, factory or None, can_reverse),
        )
    conn.close()


def delete_agv(name):
    """Delete an AGV by name."""
    _ensure_table()
    conn = _db_conn()
    if not conn:
        return
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DELETE FROM agv_devices WHERE name = %s", (name,))
    conn.close()


# ✅ FIX: truyền lang vào agv_card thay vì dùng biến lang global
def agv_card(row, lang: str = "vi"):
    badge_color = "success" if row["status"].lower() == "online" else "secondary"
    map_text = row.get("map_id") or "—"
    agv_type_label = row.get("agv_type", "")
    return dbc.Card(
        [
            dbc.CardImg(
                src=row.get("icon", "/assets/agv_icon.png"),
                top=True,
                style={
                    "height": "110px",
                    "objectFit": "contain",
                    "padding": "10px",
                    "filter": "drop-shadow(0 12px 22px rgba(0,0,0,0.45)) brightness(1.05)",
                },
            ),
            dbc.CardBody(
                [
                    html.H5(row["name"], className="card-title text-white mb-1"),
                    html.P(f"Type: {agv_type_label}", className="card-text mb-1 text-white-50", style={"fontSize": "12px"}),
                    html.P(f"IP: {row['ip']}", className="card-text mb-1 text-white-50", style={"fontSize": "12px"}),
                    html.P(f"Port: {row['port']}", className="card-text mb-1 text-white-50", style={"fontSize": "12px"}),
                    html.P(f"Factory: {row.get('factory') or '—'}", className="card-text mb-1 text-white-50", style={"fontSize": "12px"}),
                    html.P(
                        [html.Span("Map: ", style={"opacity": ".6"}), html.Span(map_text, style={"color": "#adc6ff", "fontWeight": "600"})],
                        className="card-text mb-2",
                        style={"fontSize": "12px"},
                    ),
                    dbc.Badge(row["status"], color=badge_color, className="px-2 py-1"),
                    dbc.Badge(
                        t(lang, "agv.forward_only_badge", "⇢ Chỉ 1 chiều tiến"),
                        color="warning", className="px-2 py-1 ms-1",
                    ) if not row.get("can_reverse", True) else None,
                ],
                style={"textAlign": "center"},
            ),
            dbc.CardFooter(
                dbc.ButtonGroup(
                    [
                        dbc.Button(
                            t(lang, "agv.configure", "Configure"),
                            id={"type": "configure-agv", "name": row["name"]},
                            color="primary",
                            size="sm",
                            outline=True,
                            className="me-1",
                            n_clicks=0,
                        ),
                        dbc.Button(
                            t(lang, "agv.delete", "Delete"),
                            id={"type": "delete-agv", "name": row["name"]},
                            color="danger",
                            size="sm",
                            outline=True,
                            n_clicks=0,
                        ),
                    ],
                    style={"width": "100%", "display": "flex", "justifyContent": "center"},
                ),
                style={"background": "transparent", "borderTop": "1px solid rgba(255,255,255,0.08)"},
            ),
        ],
        className="agv-card",
        style={"width": "100%", "margin": "0"},
    )


def layout(lang: str = "vi"):
    from i18n import t, normalize_lang
    lang = normalize_lang(lang)
    return html.Div(
        [
            dcc.Store(id="agv-store", data=[]),
            dcc.Interval(id="agv-refresh", interval=3000, n_intervals=0),
            dbc.Container(
                [
                    dbc.Row(
                        [
                            dbc.Col(
                                html.H3(
                                    t(lang, "agv.title", "AGV Manager"),
                                    className="text-white my-3",
                                ),
                                width="auto",
                            ),
                            dbc.Col(
                                dbc.Button(
                                    t(lang, "agv.add", "+ Add AGV"),
                                    id="btn-add-agv",
                                    color="success",
                                    size="md",
                                    className="mt-2",
                                    style={"padding": "8px 14px", "fontWeight": "600"},
                                ),
                                width="auto",
                                style={"textAlign": "right", "flex": "1"},
                            ),
                        ],
                        align="center",
                        className="g-2 mb-2 justify-content-between",
                    ),
                    html.Div(
                        id="agv-card-container",
                        style={
                            "display": "grid",
                            "gridTemplateColumns": "repeat(auto-fill, minmax(240px, 1fr))",
                            "gap": "16px",
                            "paddingBottom": "24px",
                            "alignItems": "stretch",
                        },
                    ),
                ],
                fluid=True,
            ),
            html.Div(
                id="add-agv-panel",
                style={
                    "position": "fixed",
                    "top": "0",
                    "right": "-420px",
                    "width": "400px",
                    "height": "100vh",
                    "background": "rgba(15,23,42,0.95)",
                    "color": "white",
                    "zIndex": "1500",
                    "boxShadow": "0 0 30px rgba(0,0,0,0.45)",
                    "borderLeft": "1px solid rgba(255,255,255,0.1)",
                    "transition": "right 0.35s ease",
                    "padding": "18px",
                },
                children=[
                    html.H4(t(lang, "agv.add_panel.title", "Add New AGV"), className="mb-1 text-white"),
                    html.P(
                        t(lang, "agv.add_panel.desc", "Select type and map. Other settings will be configured later via Config Mode."),
                        style={"fontSize": "12px", "color": "#8c909f", "marginBottom": "20px"},
                    ),

                    dbc.Label(t(lang, "agv.type_label", "AGV Type"), className="mb-1",
                              style={"fontSize": "13px", "color": "#c2c6d6", "fontWeight": "600"}),
                    dcc.Dropdown(
                        id="add-agv-type",
                        options=[
                            {"label": t(lang, "agv.type.carry",   "AGV Carry (tow load — Line)"),    "value": "carry"},
                            {"label": t(lang, "agv.type.tow",     "AGV Tow (tow cart — Line)"),      "value": "tow"},
                            {"label": t(lang, "agv.type.trailer", "AGV Trailer (tow trailer — Line)"), "value": "trailer"},
                            {"label": t(lang, "agv.type.slam",    "AGV Slam / QR Code (VDA5050)"),   "value": "slam_qr"},
                        ],
                        placeholder=t(lang, "agv.placeholder.type", "Select AGV type..."),
                        className="mb-3",
                        style={"color": "#000"},
                    ),

                    dbc.Switch(
                        id="add-agv-cannot-reverse",
                        label=t(lang, "agv.cannot_reverse_label",
                                "Xe chỉ đi 1 chiều tiến (đầu kéo/rơ-moóc — không lùi được)"),
                        value=False,
                        className="mb-4",
                        label_style={"color": "#fff", "fontSize": "12px"},
                    ),

                    dbc.Label(t(lang, "agv.map_label", "Map"), className="mb-1",
                              style={"fontSize": "13px", "color": "#c2c6d6", "fontWeight": "600"}),
                    dcc.Dropdown(
                        id="add-agv-map",
                        options=[{"label": m["name"], "value": m["id"]} for m in load_maps()],
                        placeholder=t(lang, "agv.placeholder.map", "Select map..."),
                        className="mb-2",
                        clearable=True,
                        style={"color": "#000"},
                    ),
                    html.Small(
                        t(lang, "agv.line_hint", "💡 Line AGV needs a map to show position via RFID tag."),
                        style={"color": "#8c909f", "fontSize": "11px", "display": "block", "marginBottom": "16px"},
                    ),

                    # Nhà máy (factory) — dùng chung namespace topic MQTT cho mọi xe cùng
                    # nhà máy (uagv/v{2,3}/{factory}/{agv_id}/...). Chọn từ nhà máy đã có
                    # sẵn để tránh gõ lệch chính tả, hoặc gõ tên mới nếu là nhà máy đầu tiên.
                    dbc.Label(t(lang, "agv.factory_label", "Nhà máy (Factory)"), className="mb-1",
                              style={"fontSize": "13px", "color": "#c2c6d6", "fontWeight": "600"}),
                    dcc.Dropdown(
                        id="add-agv-factory-select",
                        options=[],
                        placeholder=t(lang, "agv.placeholder.factory_existing", "Chọn nhà máy đã có…"),
                        className="mb-2",
                        clearable=True,
                        style={"color": "#000"},
                    ),
                    dbc.Input(
                        id="add-agv-factory",
                        placeholder=t(lang, "agv.placeholder.factory_new", "…hoặc nhập tên nhà máy mới"),
                        value="",
                        className="mb-3",
                    ),

                    # Default info display
                    html.Div(
                        [
                            html.Div(t(lang, "agv.default_info_title", "Default values on creation:"), style={"fontSize": "11px", "color": "#8c909f", "marginBottom": "6px", "fontWeight": "600"}),
                            html.Div([html.Span(t(lang, "agv.default_name_lbl", "AGV Name: "), style={"color": "#8c909f"}), html.Span(t(lang, "agv.default_name_val", "Auto-generated (AGVxxx)"), style={"color": "#adc6ff", "fontFamily": "monospace"})], style={"fontSize": "11px", "marginBottom": "3px"}),
                            html.Div([html.Span("IP / Port: ", style={"color": "#8c909f"}), html.Span(t(lang, "agv.default_ip", "Not configured"), style={"color": "#555"})], style={"fontSize": "11px"}),
                        ],
                        style={"background": "rgba(255,255,255,.04)", "border": "1px solid rgba(255,255,255,.08)", "borderRadius": "8px", "padding": "10px 12px", "marginBottom": "20px"},
                    ),

                    # Hidden inputs
                    dbc.Input(id="add-agv-name",    value="", style={"display": "none"}),
                    dbc.Input(id="add-agv-ip",      value="", style={"display": "none"}),
                    dbc.Input(id="add-agv-port",    value="", style={"display": "none"}),

                    dbc.Button(t(lang, "agv.add", "+ Add AGV"), id="btn-save-agv", color="primary", className="me-2",
                               style={"fontWeight": "600"}),
                    dbc.Button(t(lang, "agv.btn.close", "Close"), id="btn-close-agv", color="secondary", outline=True),
                ],
            ),
            # ── Modal điều khiển AGV (mở khi click "Cấu hình") ────────────
            dbc.Modal(
                [
                    dbc.ModalBody(
                        html.Iframe(
                            id="ctrl-iframe",
                            src="",
                            style={
                                "width": "100%",
                                "height": "580px",
                                "border": "none",
                                "borderRadius": "12px",
                            },
                        ),
                        style={"padding": "0", "background": "#0b1326", "borderRadius": "14px"},
                    ),
                ],
                id="ctrl-modal",
                is_open=False,
                size="lg",
                centered=True,
                backdrop=True,
                style={"maxWidth": "420px"},
                contentClassName="border-0",
            ),
            dcc.Store(id="ctrl-agv-name", data=""),
        ]
    )


@callback(
    Output("add-agv-panel", "style"),
    Input("btn-add-agv", "n_clicks"),
    Input("btn-close-agv", "n_clicks"),
    State("add-agv-panel", "style"),
    prevent_initial_call=True,
)
def toggle_panel(open_click, close_click, current_style):
    if not current_style:
        current_style = {}
    ctx = dash.callback_context
    if not ctx.triggered:
        return current_style
    trigger = ctx.triggered[0]["prop_id"].split(".")[0]
    if trigger == "btn-add-agv":
        current_style["right"] = "0px"
    elif trigger == "btn-close-agv":
        current_style["right"] = "-420px"
    return current_style


@callback(
    Output("add-agv-map", "options"),
    Input("btn-add-agv", "n_clicks"),
    prevent_initial_call=True,
)
def populate_map_dropdown(_):
    maps = load_maps()
    return [{"label": m["name"], "value": m["id"]} for m in maps]


@callback(
    Output("add-agv-factory-select", "options"),
    Input("btn-add-agv", "n_clicks"),
    prevent_initial_call=True,
)
def populate_factory_dropdown(_):
    return [{"label": f, "value": f} for f in load_factories()]


@callback(
    Output("add-agv-factory", "value", allow_duplicate=True),
    Input("add-agv-factory-select", "value"),
    prevent_initial_call=True,
)
def apply_factory_selection(selected):
    # Chọn 1 nhà máy có sẵn trong dropdown → điền luôn vào ô nhập bên dưới (ô
    # nhập vẫn dùng được để gõ tên nhà máy MỚI nếu bỏ trống dropdown).
    if not selected:
        raise dash.exceptions.PreventUpdate
    return selected


@callback(
    Output("agv-store", "data"),
    Output("add-agv-panel", "style", allow_duplicate=True),
    Output("add-agv-name", "value"),
    Output("add-agv-factory", "value"),
    Output("add-agv-factory-select", "value"),
    Output("add-agv-ip", "value"),
    Output("add-agv-port", "value"),
    Output("add-agv-type", "value"),
    Output("add-agv-map", "value"),
    Output("add-agv-cannot-reverse", "value"),
    Input("btn-save-agv", "n_clicks"),
    State("add-agv-name", "value"),
    State("add-agv-factory", "value"),
    State("add-agv-ip", "value"),
    State("add-agv-port", "value"),
    State("add-agv-type", "value"),
    State("add-agv-map", "value"),
    State("add-agv-cannot-reverse", "value"),
    State("agv-store", "data"),
    State("add-agv-panel", "style"),
    prevent_initial_call=True,
)
def save_agv(n_clicks, name, factory, ip, port, agv_type, map_id, cannot_reverse, data, style):
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    if not agv_type:
        raise dash.exceptions.PreventUpdate

    # Tự sinh tên AGV dạng "AGV01", "AGV02" … dựa trên số AGV hiện có
    existing = load_agvs()
    auto_idx = len(existing) + 1
    auto_name = f"AGV{auto_idx:02d}"
    # Nhà máy: dùng đúng giá trị người dùng chọn/gõ ở panel (chọn từ dropdown
    # nhà máy đã có, hoặc gõ tên mới nếu là nhà máy đầu tiên) — mọi xe cùng nhà
    # máy nên dùng chung 1 giá trị này để cùng 1 namespace topic MQTT
    # (uagv/v{2,3}/{factory}/{agv_id}/...). Rơi về "tot" nếu bỏ trống hoàn toàn.
    final_factory = (factory or "").strip() or "tot"

    upsert_agv(auto_name, agv_type, ip=None, port=None,
               map_id=map_id or None, factory=final_factory,
               can_reverse=not bool(cannot_reverse))
    # Reload registry trên server để AGV mới ngay lập tức được nhận diện
    try:
        import requests as _req
        _req.post("http://localhost:8000/api/registry/reload", timeout=2)
    except Exception:
        pass
    data = load_agvs()
    if style is None:
        style = {}
    style["right"] = "-420px"
    return data, style, "", "", None, "", "", None, None, False


# ── Callback: mở modal khi click nút "Cấu hình" ─────────────────────────────
from dash import ALL as _ALL

@callback(
    Output("ctrl-modal",    "is_open"),
    Output("ctrl-iframe",   "src"),
    Input({"type": "configure-agv", "name": _ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def open_ctrl_modal(n_clicks_list):
    ctx = dash.callback_context
    if not ctx.triggered or not any(n_clicks_list):
        raise dash.exceptions.PreventUpdate
    # Lấy tên AGV từ id của button được click
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]
    import json as _json
    agv_name = _json.loads(triggered_id).get("name", "")
    if not agv_name:
        raise dash.exceptions.PreventUpdate
    src = f"/assets/agv_manager.html?auto_open={agv_name}"
    return True, src


@callback(
    Output("ctrl-modal", "is_open", allow_duplicate=True),
    Input("ctrl-modal",  "is_open"),
    prevent_initial_call=True,
)
def _noop_ctrl(_): raise dash.exceptions.PreventUpdate


# ✅ FIX: lấy lang từ Store global "lang-store" (được tạo ở main.py)
@callback(
    Output("agv-card-container", "children"),
    Input("agv-store", "data"),
    State("lang-store", "data"),
)
def render_cards(data, lang):
    from i18n import normalize_lang
    lang = normalize_lang(lang)

    if not data:
        return html.Div(t(lang, "agv.none", "No AGV available"), className="text-white-50")
    return [agv_card(r, lang) for r in data]


@callback(
    Output("agv-store", "data", allow_duplicate=True),
    Input("agv-refresh", "n_intervals"),
    prevent_initial_call="initial_duplicate",
)
def refresh_agvs(_):
    return load_agvs()


@callback(
    Output("agv-store", "data", allow_duplicate=True),
    Input({"type": "delete-agv", "name": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def remove_agv(delete_clicks):
    # Không làm gì nếu chưa có click xóa thực sự
    if not delete_clicks or all(not c for c in delete_clicks):
        raise dash.exceptions.PreventUpdate

    ctx = dash.callback_context
    triggered_id = ctx.triggered_id
    if isinstance(triggered_id, dict) and triggered_id.get("name"):
        delete_agv(triggered_id["name"])
        return load_agvs()

    raise dash.exceptions.PreventUpdate
