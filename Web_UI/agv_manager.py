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

STATUS_THRESHOLD_SECONDS = 3
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
                    last_seen   TIMESTAMPTZ,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                """
            )
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


def load_agvs():
    """Fetch AGV list from DB; fallback to empty list if DB unavailable."""
    _ensure_table()
    conn = _db_conn()
    if not conn:
        return []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name, agv_type, ip, port, last_seen FROM agv_devices ORDER BY name"
        )
        rows = cur.fetchall()
    conn.close()
    result = []
    for name, agv_type, ip, port, last_seen in rows:
        result.append(
            {
                "name": name,
                "ip": str(ip) if ip else "",
                "port": str(port) if port else "",
                "status": _status_from_last_seen(last_seen),
                "icon": _icon_for_type(agv_type),
            }
        )
    return result


def upsert_agv(name, agv_type, ip, port):
    """Insert/update AGV without touching last_seen (stays NULL until real heartbeat)."""
    _ensure_table()
    conn = _db_conn()
    if not conn:
        return
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agv_devices (name, agv_type, ip, port, last_seen)
            VALUES (%s, %s, %s, %s, NULL)
            ON CONFLICT (name) DO UPDATE
              SET agv_type = EXCLUDED.agv_type,
                  ip = EXCLUDED.ip,
                  port = EXCLUDED.port
            """,
            (name, agv_type or "trailer", ip, port),
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
    return dbc.Card(
        [
            dbc.CardImg(
                src=row.get("icon", "/assets/agv_icon.png"),
                top=True,
                style={
                    "height": "120px",
                    "objectFit": "contain",
                    "padding": "12px",
                    "filter": "drop-shadow(0 12px 22px rgba(0,0,0,0.45)) brightness(1.05)",
                },
            ),
            dbc.CardBody(
                [
                    html.H5(row["name"], className="card-title text-white"),
                    html.P(f"IP: {row['ip']}", className="card-text mb-1 text-white-50"),
                    html.P(f"Port: {row['port']}", className="card-text mb-2 text-white-50"),
                    dbc.Badge(row["status"], color=badge_color, className="px-2 py-1"),
                ],
                style={"textAlign": "center"},
            ),
            dbc.CardFooter(
                dbc.ButtonGroup(
                    [
                        dbc.Button(
                            t(lang, "agv.configure", "Configure"),
                            color="primary",
                            size="sm",
                            outline=True,
                            className="me-1",
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
                    html.H4(t(lang, "agv.modal.add_title", "Add AGV"), className="mb-3"),
                    dbc.Input(id="add-agv-name", placeholder=t(lang, "agv.modal.name", "AGV Name"), className="mb-3"),
                    dbc.Input(id="add-agv-ip", placeholder=t(lang, "agv.modal.ip", "IP Address"), className="mb-3"),
                    dbc.Input(id="add-agv-port", placeholder="Port", type="number", className="mb-3"),
                    dbc.Label("AGV Type", className="mt-2"),
                    dcc.Dropdown(
                        id="add-agv-type",
                        options=[
                            {"label": "AGV Slam/QR Code", "value": "slam_qr"},
                            {"label": "AGV Carry", "value": "carry"},
                            {"label": "AGV Tow", "value": "tow"},
                            {"label": "AGV Trailer", "value": "trailer"},
                        ],
                        placeholder="Chon loai AGV",
                        className="mb-3",
                    ),
                    dbc.Button(t(lang, "agv.modal.save", "Save"), id="btn-save-agv", color="primary", className="me-2"),
                    dbc.Button("Close", id="btn-close-agv", color="secondary", outline=True),
                ],
            ),
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
    Output("agv-store", "data"),
    Output("add-agv-panel", "style", allow_duplicate=True),
    Output("add-agv-name", "value"),
    Output("add-agv-ip", "value"),
    Output("add-agv-port", "value"),
    Output("add-agv-type", "value"),
    Input("btn-save-agv", "n_clicks"),
    State("add-agv-name", "value"),
    State("add-agv-ip", "value"),
    State("add-agv-port", "value"),
    State("add-agv-type", "value"),
    State("agv-store", "data"),
    State("add-agv-panel", "style"),
    prevent_initial_call=True,
)
def save_agv(n_clicks, name, ip, port, agv_type, data, style):
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    upsert_agv(name or "AGV", agv_type or "trailer", ip, port)
    data = load_agvs()
    if style is None:
        style = {}
    style["right"] = "-420px"
    return data, style, "", "", "", None


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
