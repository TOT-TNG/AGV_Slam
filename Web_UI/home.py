from dash import html, dcc, Input, Output, State, callback, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import dash
import requests as _req

from i18n import t, normalize_lang

_API = "http://localhost:8000"

_CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="white", family="Inter, system-ui, sans-serif", size=11),
    margin=dict(l=6, r=6, t=32, b=6),
    legend=dict(
        bgcolor="rgba(0,0,0,0)",
        font=dict(color="rgba(255,255,255,.8)", size=11),
        orientation="h", x=0, y=1.18,
    ),
    xaxis=dict(
        tickfont=dict(color="rgba(255,255,255,.6)", size=10),
        gridcolor="rgba(255,255,255,.05)",
        linecolor="rgba(0,0,0,0)",
        showgrid=True, zeroline=False,
    ),
    yaxis=dict(
        tickfont=dict(color="rgba(255,255,255,.6)", size=10),
        gridcolor="rgba(255,255,255,.07)",
        linecolor="rgba(0,0,0,0)",
        showgrid=True, zeroline=False,
    ),
    hoverlabel=dict(bgcolor="rgba(5,13,30,.96)", font_color="white",
                    bordercolor="rgba(255,255,255,.15)", font_size=12),
)

_STATUS_COLORS = {
    "completed": "#34d399", "failed": "#fb7185",
    "cancelled": "#94a3b8", "running": "#fbbf24", "queued": "#a78bfa",
}
_STATUS_LABELS = {
    "completed": "Hoàn thành", "failed": "Thất bại",
    "cancelled": "Đã hủy", "running": "Đang chạy", "queued": "Hàng chờ",
}


_CARD_BASE = {
    "background": "rgba(10,18,36,.88)",
    "border": "1px solid rgba(255,255,255,.08)",
    "borderRadius": "16px",
    "backdropFilter": "blur(6px)",
}

_LBL = {
    "fontSize": "10px", "fontWeight": "700",
    "color": "rgba(255,255,255,.45)", "textTransform": "uppercase",
    "letterSpacing": ".09em",
}


def _kpi_card(label, value, color, sublabel=None, icon=None):
    return html.Div(
        [
            # Accent stripe
            html.Div(style={
                "width": "32px", "height": "3px",
                "background": color, "borderRadius": "2px", "marginBottom": "12px",
            }),
            html.Div(label, style=_LBL),
            html.Div(
                str(value) if value is not None else "—",
                style={
                    "fontSize": "36px", "fontWeight": "800", "color": color,
                    "fontFamily": "'JetBrains Mono',monospace",
                    "lineHeight": "1.1", "marginTop": "4px",
                },
            ),
            html.Div(sublabel, style={
                "fontSize": "11px", "color": "rgba(255,255,255,.35)", "marginTop": "5px",
            }) if sublabel else None,
        ],
        style={**_CARD_BASE, "padding": "18px 22px"},
    )


def _agv_status_card(agv):
    agv_id    = agv.get("agv_id", "?")
    is_online = agv.get("connection", "OFFLINE") == "ONLINE"
    is_drv    = bool(agv.get("driving"))
    is_busy   = bool(agv.get("is_busy"))
    paused    = bool(agv.get("paused"))
    battery   = agv.get("battery")
    node      = agv.get("current_node")

    if not is_online:
        status_label, status_color = "Ngoại tuyến",    "#64748b"
    elif paused:
        status_label, status_color = "Tạm dừng",       "#fbbf24"
    elif is_drv:
        status_label, status_color = "Di chuyển",      "#34d399"
    elif is_busy:
        status_label, status_color = "Thực hiện",      "#a78bfa"
    else:
        status_label, status_color = "Chờ lệnh",       "#94a3b8"

    batt_pct   = int(battery) if battery is not None else None
    batt_color = (
        "#34d399" if batt_pct is not None and batt_pct > 50 else
        "#fbbf24" if batt_pct is not None and batt_pct > 20 else
        "#fb7185"
    ) if batt_pct is not None else "#475569"

    return html.Div(
        [
            # Header: dot + ID
            html.Div(
                [
                    html.Span(style={
                        "width": "8px", "height": "8px", "borderRadius": "50%",
                        "background": status_color,
                        "boxShadow": f"0 0 6px {status_color}",
                        "flexShrink": "0",
                        "display": "inline-block",
                    }),
                    html.Span(agv_id, style={
                        "fontFamily": "'JetBrains Mono',monospace",
                        "fontWeight": "700", "fontSize": "15px", "color": "#fff",
                    }),
                ],
                style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "8px"},
            ),
            # Status badge
            html.Div(
                status_label,
                style={
                    "display": "inline-block",
                    "fontSize": "10px", "fontWeight": "700",
                    "color": status_color,
                    "background": f"{status_color}18",
                    "border": f"1px solid {status_color}40",
                    "borderRadius": "6px", "padding": "2px 8px",
                    "marginBottom": "10px", "letterSpacing": ".04em",
                },
            ),
            # Battery bar
            html.Div(
                [
                    html.Span("BATTERY", style={**_LBL, "fontSize": "9px"}),
                    html.Div(
                        [
                            html.Div(style={
                                "flex": "1", "height": "4px",
                                "background": "rgba(255,255,255,.1)",
                                "borderRadius": "2px", "overflow": "hidden",
                            }, children=[
                                html.Div(style={
                                    "width": f"{batt_pct}%" if batt_pct is not None else "0%",
                                    "height": "100%", "background": batt_color, "borderRadius": "2px",
                                    "transition": "width .4s ease",
                                }),
                            ]),
                            html.Span(
                                f"{batt_pct}%" if batt_pct is not None else "—",
                                style={"fontSize": "11px", "color": batt_color,
                                       "fontFamily": "'JetBrains Mono',monospace",
                                       "minWidth": "32px", "textAlign": "right"},
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center", "gap": "8px", "marginTop": "3px"},
                    ),
                ],
                style={"marginBottom": "8px"},
            ) if batt_pct is not None else None,
            # Node
            html.Div(
                [
                    html.Span("NODE", style={**_LBL, "fontSize": "9px"}),
                    html.Span(f" {node}", style={"fontSize": "12px", "color": "rgba(255,255,255,.75)",
                                                  "fontFamily": "'JetBrains Mono',monospace",
                                                  "fontWeight": "600", "marginLeft": "6px"}),
                ],
                style={"display": "flex", "alignItems": "center"},
            ) if node else None,
        ],
        style={
            **_CARD_BASE,
            "borderLeft": f"3px solid {status_color}",
            "padding": "14px 16px",
            "opacity": "1" if is_online else "0.45",
            "transition": "opacity .3s",
        },
    )


# ======= SIDEBAR (factory) =======
def make_sidebar(lang: str, pathname: str = ""):
    lang = normalize_lang(lang)
    p = pathname or ""

    # Submenu containers
    map_cls  = "submenu open" if p in MAP_PATHS  else "submenu"
    task_cls = "submenu open" if p in TASK_PATHS else "submenu"
    log_cls  = "submenu open" if p in LOG_PATHS  else "submenu"

    # Helper: compute className for menu items and submenu items
    def mi(active):  return "menu-item active"  if active else "menu-item"
    def si(active):  return "submenu-item active" if active else "submenu-item"

    is_home              = p in {"/home", "/home/"}
    is_map               = p in MAP_PATHS
    is_agv               = p in {"/agv-manager", "/home/agv-manager"}
    is_task              = p in TASK_PATHS
    is_log               = p in LOG_PATHS
    is_create_map        = p in {"/create-map",        "/home/create-map"}
    is_task_create       = p in {"/task-create",       "/home/task-create"}
    is_task_list         = p in {"/task-manager",      "/home/task-manager", "/task-list"}
    is_task_execute      = p in {"/task-execute",      "/home/task-execute"}
    is_journal_history   = p in {"/journal-history",   "/home/journal-history"}
    is_journal_logs      = p in {"/journal-logs",      "/home/journal-logs"}

    return html.Div(
        [
            html.Div(t(lang, "app.title", "TOT ACS"), className="menu-logo"),
            html.Div(
                [
                    html.Div(
                        [html.I(className="bi bi-house-door me-2"), html.Span(t(lang, "menu.home", "Home"))],
                        className=mi(is_home),
                        id="menu-home",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [html.I(className="bi bi-map me-2"), html.Span(t(lang, "menu.map", "Map"))],
                                className=mi(is_map),
                                id="menu-map",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        t(lang, "menu.map.create", "Create Map"),
                                        id="submenu-create-map",
                                        className=si(is_create_map),
                                    ),
                                    html.A(
                                        t(lang, "menu.map.agvmap", "Bản đồ theo dõi"),
                                        href="/assets/task_execute.html?view=monitor",
                                        target="_blank",
                                        className="submenu-item",
                                        style={"textDecoration": "none", "color": "inherit"},
                                    ),
                                ],
                                id="submenu-map",
                                className=map_cls,
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            html.Div(
                                [html.I(className="bi bi-list-task me-2"), html.Span(t(lang, "menu.task", "Task Manager"))],
                                className=mi(is_task),
                                id="menu-task",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        t(lang, "menu.task.create", "Create Task"),
                                        id="submenu-task-create",
                                        className=si(is_task_create),
                                    ),
                                    html.Div(
                                        t(lang, "menu.task.list", "Task List"),
                                        id="submenu-task-list",
                                        className=si(is_task_list),
                                    ),
                                    html.Div(
                                        t(lang, "menu.task.execute", "Thực hiện tác vụ"),
                                        id="submenu-task-execute",
                                        className=si(is_task_execute),
                                    ),
                                ],
                                id="submenu-task",
                                className=task_cls,
                            ),
                        ]
                    ),
                    html.Div(
                        [html.I(className="bi bi-cpu me-2"), html.Span(t(lang, "menu.agv", "AGV Manager"))],
                        className=mi(is_agv),
                        id="menu-agv-manager",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [html.I(className="bi bi-journal-text me-2"), html.Span(t(lang, "menu.log", "Nhật ký"))],
                                className=mi(is_log),
                                id="menu-log",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        t(lang, "menu.log.history", "Lịch sử hoạt động"),
                                        id="submenu-journal-history",
                                        className=si(is_journal_history),
                                    ),
                                    html.Div(
                                        t(lang, "menu.log.logs", "Logs"),
                                        id="submenu-journal-logs",
                                        className=si(is_journal_logs),
                                    ),
                                ],
                                id="submenu-log",
                                className=log_cls,
                            ),
                        ]
                    ),
                    html.Div(
                        [html.I(className="bi bi-bar-chart-line me-2"), html.Span(t(lang, "menu.stat", "Statistic"))],
                        className="menu-item",
                        id="menu-stat",
                    ),
                    html.Div(
                        [html.I(className="bi bi-question-circle me-2"), html.Span(t(lang, "menu.help", "Help"))],
                        className="menu-item",
                        id="menu-help",
                    ),
                ],
                className="menu-list",
            ),
        ],
        className="sidebar",
    )


# ======= TOPBAR (factory) =======
def make_topbar(lang: str):
    lang = normalize_lang(lang)
    abbr = "VIE" if lang == "vi" else "ENG"

    return html.Div(
        [
            html.Div(t(lang, "topbar.title", "AGV Control System (ACS)"), className="topbar-title"),
            html.Div(
                [
                    # ── MQTT mode toggle ───────────────────────────────────────
                    dcc.Interval(id="mqtt-mode-interval", interval=5000, n_intervals=0),
                    html.Div(
                        id="mqtt-mode-container",
                        style={"display": "flex", "alignItems": "center", "gap": "6px"},
                        children=[
                            html.Span(id="mqtt-mode-badge", style={
                                "fontSize": "10px", "fontFamily": "monospace",
                                "padding": "3px 8px", "borderRadius": "6px",
                                "background": "rgba(255,255,255,.07)",
                                "border": "1px solid rgba(255,255,255,.12)",
                                "color": "#8c909f",
                            }, children="MQTT: …"),
                            html.Button(
                                id="btn-switch-mqtt",
                                n_clicks=0,
                                style={
                                    "fontSize": "10px", "padding": "3px 9px",
                                    "borderRadius": "6px",
                                    "background": "rgba(255,255,255,.07)",
                                    "border": "1px solid rgba(255,255,255,.12)",
                                    "color": "#c2c6d6", "cursor": "pointer",
                                },
                                children="Đổi",
                            ),
                        ],
                    ),
                    # ──────────────────────────────────────────────────────────
                    html.Div(
                        [
                            html.Button(
                                [
                                    html.I(className="bi bi-globe2", style={"marginRight": "8px"}),
                                    html.Span(abbr, style={"fontWeight": "800"}),
                                    html.I(className="bi bi-caret-down-fill", style={"marginLeft": "10px"}),
                                ],
                                id="lang-toggle",
                                n_clicks=0,
                                style={
                                    "display": "inline-flex",
                                    "alignItems": "center",
                                    "justifyContent": "center",
                                    "padding": "6px 12px",
                                    "borderRadius": "10px",
                                    "background": "rgba(255,255,255,0.08)",
                                    "border": "1px solid rgba(255,255,255,0.12)",
                                    "color": "white",
                                    "cursor": "pointer",
                                    "whiteSpace": "nowrap",
                                },
                            ),
                        ],
                        style={
                            "position": "relative",
                            "display": "inline-block",
                            "zIndex": "1000",
                            "overflow": "visible",
                        },
                    ),
                    html.Div(
                        [
                            html.Img(
                                src="https://img.icons8.com/ios-filled/50/ffffff/user.png",
                                id="account-icon",
                                className="account-icon",
                                style={"cursor": "pointer"},
                            ),
                            html.Div(
                                id="account-menu",
                                children=[
                                    html.Div(
                                        t(lang, "account.logout", "Logout"),
                                        id="logout-btn",
                                        className="account-item",
                                    )
                                ],
                                style={"display": "none"},
                            ),
                        ],
                        id="account-container",
                        style={"position": "relative"},
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "gap": "12px",
                    "flexWrap": "nowrap",
                    "whiteSpace": "nowrap",
                },
            ),
        ],
        className="topbar",
        style={"display": "flex", "alignItems": "center", "justifyContent": "space-between"},
    )


# ======= HOME CONTENT (factory) =======
def home_layout(lang: str):
    lang = normalize_lang(lang)

    _sec_hdr = {
        "fontSize": "10px", "fontWeight": "700",
        "color": "rgba(255,255,255,.4)", "textTransform": "uppercase",
        "letterSpacing": ".1em", "marginBottom": "14px",
    }

    return html.Div(
        [
            dcc.Interval(id="home-refresh-interval", interval=10_000, n_intervals=0),

            # ── Tiêu đề ───────────────────────────────────────────────────────
            html.Div(
                t(lang, "home.title", "Tổng quan hệ thống"),
                style={
                    "fontSize": "22px", "fontWeight": "700", "color": "#fff",
                    "marginBottom": "20px", "letterSpacing": "-.02em",
                },
            ),

            # ── KPI Row: 6 equal columns ───────────────────────────────────────
            html.Div(
                [
                    html.Div("Nhiệm vụ — Tháng này", style={**_sec_hdr, "marginBottom": "10px"}),
                    html.Div(
                        id="home-kpi-row",
                        style={
                            "display": "grid",
                            "gridTemplateColumns": "repeat(6, 1fr)",
                            "gap": "12px",
                        },
                    ),
                ],
                style={"marginBottom": "16px"},
            ),

            # ── Charts Row: bar+line (5fr) | doughnut (3fr) ───────────────────
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Nhiệm vụ theo ngày", style=_sec_hdr),
                            dcc.Graph(
                                id="home-chart-trips",
                                config={"displayModeBar": False},
                                style={"height": "210px", "marginTop": "-8px"},
                            ),
                        ],
                        style={**_CARD_BASE, "padding": "18px 20px"},
                    ),
                    html.Div(
                        [
                            html.Div("Phân bổ trạng thái", style=_sec_hdr),
                            dcc.Graph(
                                id="home-chart-status",
                                config={"displayModeBar": False},
                                style={"height": "210px", "marginTop": "-8px"},
                            ),
                        ],
                        style={**_CARD_BASE, "padding": "18px 20px", "overflow": "visible"},
                    ),
                ],
                style={
                    "display": "grid",
                    "gridTemplateColumns": "5fr 3fr",
                    "gap": "12px",
                    "marginBottom": "16px",
                },
            ),

            # ── AGV Status Row ────────────────────────────────────────────────
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Trạng thái AGV", style=_sec_hdr),
                            html.Span(
                                id="home-agv-online-badge",
                                style={
                                    "fontSize": "11px", "color": "#34d399",
                                    "fontWeight": "700", "marginLeft": "10px",
                                },
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center", "marginBottom": "12px"},
                    ),
                    html.Div(
                        id="home-agv-row",
                        style={
                            "display": "grid",
                            "gridTemplateColumns": "repeat(auto-fill, minmax(190px, 1fr))",
                            "gap": "12px",
                        },
                    ),
                ],
                style={**_CARD_BASE, "padding": "18px 20px"},
            ),
        ],
        style={
            "width": "100%",
            "height": "calc(100vh - 68px)",
            "overflowY": "auto",
            "padding": "20px 24px",
            "boxSizing": "border-box",
            "display": "flex",
            "flexDirection": "column",
        },
    )


# ======= CALLBACKS =======

def _empty_fig():
    fig = go.Figure()
    fig.update_layout(**_CHART_LAYOUT)
    fig.add_annotation(text="Không có dữ liệu", xref="paper", yref="paper",
                       x=0.5, y=0.5, showarrow=False,
                       font=dict(color="rgba(255,255,255,.3)", size=13))
    return fig


@callback(
    Output("home-kpi-row", "children"),
    Output("home-chart-trips", "figure"),
    Output("home-chart-status", "figure"),
    Output("home-agv-row", "children"),
    Output("home-agv-online-badge", "children"),
    Input("home-refresh-interval", "n_intervals"),
    prevent_initial_call=False,
)
def refresh_home_data(_n):
    # ── Thống kê nhiệm vụ (tháng này) ─────────────────────────────────────
    kpi_row    = []
    fig_trips  = _empty_fig()
    fig_status = _empty_fig()
    try:
        r = _req.get(f"{_API}/api/statistics/tasks?period=month", timeout=3)
        if r.ok:
            data = r.json()
            # Fallback sang year nếu tháng hiện tại chưa có dữ liệu
            if data.get("summary", {}).get("total", 0) == 0:
                r2 = _req.get(f"{_API}/api/statistics/tasks?period=year", timeout=3)
                if r2.ok:
                    data = r2.json()
            s    = data.get("summary", {})
            total     = s.get("total", 0)
            completed = s.get("completed", 0)
            failed    = s.get("failed", 0)
            cancelled = s.get("cancelled", 0)
            running   = s.get("running", 0)
            avg_s     = s.get("avg_duration_s")
            pct_done  = f"{round(completed / total * 100)}% tổng" if total else None

            def _fmt_dur(sec):
                if not sec:
                    return "—"
                sec = int(sec)
                if sec < 60:
                    return f"{sec}s"
                m, s2 = divmod(sec, 60)
                return f"{m}p{s2:02d}s" if m < 60 else f"{m//60}g{m%60:02d}p"

            kpi_row = [
                _kpi_card("Tổng nhiệm vụ", total,     "#06b6d4"),
                _kpi_card("Hoàn thành",    completed, "#34d399", pct_done),
                _kpi_card("Thất bại",      failed,    "#fb7185"),
                _kpi_card("Đã hủy",        cancelled, "#94a3b8"),
                _kpi_card("Đang chạy",     running,   "#fbbf24"),
                _kpi_card("TG trung bình", _fmt_dur(avg_s), "#a78bfa", "mỗi lệnh"),
            ]

            # Bar + Line: nhiệm vụ theo ngày
            by_day = data.get("by_day", [])
            if by_day:
                xlabels     = [d2["day"][5:].replace("-", "/") for d2 in by_day]
                completed_d = [d2.get("completed", 0) for d2 in by_day]
                failed_d    = [d2.get("failed", 0) + d2.get("cancelled", 0) for d2 in by_day]
                fig_trips = go.Figure()
                fig_trips.add_trace(go.Bar(
                    x=xlabels, y=completed_d, name="Hoàn thành",
                    marker_color="rgba(52,211,153,.78)",
                    marker_line_color="#34d399", marker_line_width=1,
                    marker=dict(
                        color="rgba(52,211,153,.78)",
                        line=dict(color="#34d399", width=1),
                        cornerradius=5,
                    ),
                    hovertemplate="<b>%{x}</b><br>Hoàn thành: %{y}<extra></extra>",
                ))
                fig_trips.add_trace(go.Scatter(
                    x=xlabels, y=failed_d, name="Thất bại/Hủy",
                    mode="lines+markers",
                    line=dict(color="#fb7185", width=2.5),
                    marker=dict(
                        color="#fb7185", size=7,
                        line=dict(color="white", width=1.5),
                    ),
                    hovertemplate="<b>%{x}</b><br>Thất bại/Hủy: %{y}<extra></extra>",
                ))
                fig_trips.update_layout(**_CHART_LAYOUT)

            # Doughnut: phân bổ trạng thái
            by_status = data.get("by_status", [])
            if by_status:
                labels_s = [_STATUS_LABELS.get(r2["status"], r2["status"]) for r2 in by_status]
                values_s = [r2["count"] for r2 in by_status]
                colors_s = [_STATUS_COLORS.get(r2["status"], "#64748b") for r2 in by_status]
                fig_status = go.Figure(go.Pie(
                    labels=labels_s, values=values_s,
                    hole=0.62,
                    marker=dict(colors=colors_s, line=dict(color="rgba(10,18,36,.9)", width=3)),
                    textfont=dict(color="white", size=11),
                    textposition="none",
                    hovertemplate="<b>%{label}</b><br>%{value} (%{percent})<extra></extra>",
                ))
                _doughnut_layout = {**_CHART_LAYOUT}
                _doughnut_layout["legend"] = dict(
                    bgcolor="rgba(0,0,0,0)",
                    font=dict(color="rgba(255,255,255,.85)", size=12),
                    orientation="v",
                    x=1.04, y=0.5,
                    xanchor="left", yanchor="middle",
                )
                _doughnut_layout["margin"] = dict(l=0, r=0, t=0, b=0)
                _doughnut_layout.pop("xaxis", None)
                _doughnut_layout.pop("yaxis", None)
                fig_status.update_layout(**_doughnut_layout)
    except Exception:
        pass

    if not kpi_row:
        kpi_row = [html.Div(
            "Không thể kết nối máy chủ thống kê",
            style={"color": "rgba(255,255,255,.35)", "fontSize": "12px", "padding": "14px"},
        )]

    # ── Danh sách AGV ──────────────────────────────────────────────────────
    agv_row = []
    badge   = ""
    try:
        r = _req.get(f"{_API}/api/execute/agv-list", timeout=3)
        if r.ok:
            agvs = r.json().get("agvs", [])
            agvs_sorted = sorted(agvs, key=lambda a: (0 if a.get("connection") == "ONLINE" else 1, a.get("agv_id", "")))
            agv_row = [_agv_status_card(a) for a in agvs_sorted]
            online_n = sum(1 for a in agvs if a.get("connection") == "ONLINE")
            badge = f"⬤ {online_n}/{len(agvs)} online"
    except Exception:
        pass
    if not agv_row:
        agv_row = [html.Div(
            "Không thể tải danh sách AGV",
            style={"color": "rgba(255,255,255,.35)", "fontSize": "12px", "padding": "14px"},
        )]

    return kpi_row, fig_trips, fig_status, agv_row, badge


@callback(
    Output("account-menu", "style"),
    Input("account-icon", "n_clicks"),
    State("account-menu", "style"),
    prevent_initial_call=True,
)
def toggle_account_menu(n_clicks, style):
    if not style or style.get("display") == "none":
        return {"display": "block"}
    return {"display": "none"}


@callback(
    Output("url", "pathname", allow_duplicate=True),
    Input("logout-btn", "n_clicks"),
    prevent_initial_call=True,
)
def logout(n_clicks):
    if n_clicks:
        return "/"
    return dash.no_update


MAP_PATHS  = {"/create-map", "/home/create-map", "/map-view", "/home/map-view"}
TASK_PATHS = {"/task-create", "/home/task-create", "/task-manager", "/home/task-manager", "/task-list", "/task-execute", "/home/task-execute"}
LOG_PATHS  = {"/journal-history", "/home/journal-history", "/journal-logs", "/home/journal-logs"}




@callback(
    Output("url", "pathname", allow_duplicate=True),
    Input("submenu-create-map", "n_clicks"),
    Input("menu-home", "n_clicks"),
    Input("menu-agv-manager", "n_clicks"),
    Input("submenu-task-create", "n_clicks"),
    Input("submenu-task-list", "n_clicks"),
    Input("submenu-task-execute", "n_clicks"),
    Input("submenu-journal-history", "n_clicks"),
    Input("submenu-journal-logs", "n_clicks"),
    Input("menu-stat", "n_clicks"),
    prevent_initial_call=True,
)
def go_to_pages(create_click, home_click, agv_mgr_click,
                task_create_click, task_list_click, task_execute_click,
                journal_history_click, journal_logs_click, stat_click):
    ctx = dash.callback_context
    if not ctx.triggered:
        return no_update

    trigger = ctx.triggered[0]["prop_id"].split(".")[0]

    if trigger == "menu-home":
        return "/home"
    if trigger == "menu-agv-manager":
        return "/agv-manager"
    if trigger == "submenu-task-create":
        return "/task-create"
    if trigger == "submenu-task-list":
        return "/task-list"
    if trigger == "submenu-task-execute":
        return "/task-execute"
    if trigger == "submenu-create-map":
        return "/create-map"
    if trigger == "submenu-journal-history":
        return "/journal-history"
    if trigger == "submenu-journal-logs":
        return "/journal-logs"
    if trigger == "menu-stat":
        return "/statistics"

    return no_update




@callback(
    Output("mqtt-mode-badge", "children"),
    Output("mqtt-mode-badge", "style"),
    Input("mqtt-mode-interval", "n_intervals"),
)
def refresh_mqtt_mode(_):
    try:
        r = _req.get(f"{_API}/api/config/mqtt-mode", timeout=2)
        d = r.json()
        mode = d.get("mode", "?")
    except Exception:
        mode = "?"

    if mode == "cloud":
        label = "MQTT: CLOUD ☁"
        style = {
            "fontSize": "10px", "fontFamily": "monospace",
            "padding": "3px 8px", "borderRadius": "6px",
            "background": "rgba(0,212,255,.12)",
            "border": "1px solid rgba(0,212,255,.3)",
            "color": "#00d4ff",
        }
    elif mode == "local":
        label = "MQTT: LOCAL 🏠"
        style = {
            "fontSize": "10px", "fontFamily": "monospace",
            "padding": "3px 8px", "borderRadius": "6px",
            "background": "rgba(34,197,94,.12)",
            "border": "1px solid rgba(34,197,94,.3)",
            "color": "#22c55e",
        }
    else:
        label = "MQTT: ?"
        style = {
            "fontSize": "10px", "fontFamily": "monospace",
            "padding": "3px 8px", "borderRadius": "6px",
            "background": "rgba(255,255,255,.07)",
            "border": "1px solid rgba(255,255,255,.12)",
            "color": "#8c909f",
        }
    return label, style


@callback(
    Output("mqtt-mode-interval", "n_intervals"),
    Input("btn-switch-mqtt", "n_clicks"),
    prevent_initial_call=True,
)
def switch_mqtt(_):
    try:
        r = _req.get(f"{_API}/api/config/mqtt-mode", timeout=2)
        current = r.json().get("mode", "local")
        new_mode = "cloud" if current == "local" else "local"
        _req.post(f"{_API}/api/config/mqtt-mode",
                  json={"mode": new_mode}, timeout=5)
    except Exception:
        pass
    return 0


# Backward compatibility
sidebar = make_sidebar("vi")
topbar = make_topbar("vi")
