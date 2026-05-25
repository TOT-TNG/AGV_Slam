from dash import html, dcc, Input, Output, State, callback, no_update
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
import dash
import requests as _req

from i18n import t, normalize_lang

_API = "http://localhost:8000"

# ======= Biểu đồ minh họa (data) =======
df = pd.DataFrame({
    "Task": ["Completed", "Pending", "In Progress"],
    "Count": [45, 12, 23]
})


def _build_home_fig(lang: str):
    lang = normalize_lang(lang)
    fig = px.pie(
        df,
        names="Task",
        values="Count",
        hole=0.35,
        color="Task",
        color_discrete_map={
            "Completed": "#00d4ff",
            "Pending": "#b366ff",
            "In Progress": "#00ff9d",
        },
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="white",
        legend=dict(
            title=t(lang, "home.legend.title", "Task Status"),
            bgcolor="rgba(0,0,0,0.3)",
            bordercolor="rgba(255,255,255,0.3)",
            borderwidth=1,
            orientation="v",
            y=0.5,
            x=1.05,
            xanchor="left",
            yanchor="middle",
        ),
        height=340,
        margin=dict(l=20, r=80, t=40, b=40),
    )
    return fig


# ======= SIDEBAR (factory) =======
def make_sidebar(lang: str, pathname: str = ""):
    lang = normalize_lang(lang)
    p = pathname or ""

    # Submenu containers
    map_cls  = "submenu open" if p in MAP_PATHS  else "submenu"
    task_cls = "submenu open" if p in TASK_PATHS else "submenu"

    # Helper: compute className for menu items and submenu items
    def mi(active):  return "menu-item active"  if active else "menu-item"
    def si(active):  return "submenu-item active" if active else "submenu-item"

    is_home         = p in {"/home", "/home/"}
    is_map          = p in MAP_PATHS
    is_agv          = p in {"/agv-manager", "/home/agv-manager"}
    is_task         = p in TASK_PATHS
    is_create_map   = p in {"/create-map",    "/home/create-map"}
    is_map_cfg      = p in {"/map-configure", "/home/map-configure"}
    is_task_create  = p in {"/task-create",   "/home/task-create"}
    is_task_list    = p in {"/task-manager",  "/home/task-manager", "/task-list"}
    is_task_execute = p in {"/task-execute",  "/home/task-execute"}

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
                                    html.Div(
                                        t(lang, "menu.map.configure", "Map Configure"),
                                        id="submenu-setup-map",
                                        className=si(is_map_cfg),
                                    ),
                                    html.A(
                                        t(lang, "menu.map.agvmap", "AGV Map"),
                                        href="http://192.168.1.15:8000/AgvMap.html",
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
                        [html.I(className="bi bi-journal-text me-2"), html.Span(t(lang, "menu.log", "Log"))],
                        className="menu-item",
                        id="menu-log",
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
    fig = _build_home_fig(lang)

    return html.Div(
        [
            html.H3(t(lang, "home.title", "System Overview"), className="overview-title"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H5(
                                                t(lang, "home.card.agv_online", "AGV Online"),
                                                className="card-title mb-1",
                                            ),
                                            html.H2("12", className="mb-0"),
                                            html.P(
                                                t(lang, "home.card.agv_online.desc", "Currently active AGVs"),
                                                className="mb-0",
                                            ),
                                        ],
                                        className="summary-item",
                                    ),
                                    html.Div(
                                        [
                                            html.H5(
                                                t(lang, "home.card.tasks_today", "Tasks Today"),
                                                className="card-title mb-1",
                                            ),
                                            html.H2("234", className="mb-0"),
                                            html.P(
                                                t(lang, "home.card.tasks_today.desc", "Total tasks executed"),
                                                className="mb-0",
                                            ),
                                        ],
                                        className="summary-item",
                                    ),
                                    html.Div(
                                        [
                                            html.H5(
                                                t(lang, "home.card.errors", "Errors"),
                                                className="card-title mb-1",
                                            ),
                                            html.H2("5", className="mb-0"),
                                            html.P(
                                                t(lang, "home.card.errors.desc", "Reported system issues"),
                                                className="mb-0",
                                            ),
                                        ],
                                        className="summary-item",
                                    ),
                                ],
                                className="summary-row",
                            ),
                            html.Hr(style={"borderColor": "rgba(255,255,255,0.3)"}),
                            html.Div(
                                [
                                    html.H5(
                                        t(lang, "home.chart.title", "Task Status Distribution"),
                                        className="text-center mb-3",
                                    ),
                                    dcc.Graph(
                                        figure=fig,
                                        style={"height": "340px", "backgroundColor": "transparent"},
                                    ),
                                ]
                            ),
                        ],
                        className="white-box",
                    )
                ],
                style={"width": "100%", "display": "flex", "justifyContent": "center"},
            ),
        ],
        className="dashboard-container",
    )


# ======= CALLBACKS =======
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


MAP_PATHS  = {"/create-map", "/home/create-map", "/map-configure", "/home/map-configure", "/map-view", "/home/map-view"}
TASK_PATHS = {"/task-create", "/home/task-create", "/task-manager", "/home/task-manager", "/task-list", "/task-execute", "/home/task-execute"}




@callback(
    Output("url", "pathname", allow_duplicate=True),
    Input("submenu-create-map", "n_clicks"),
    Input("submenu-setup-map", "n_clicks"),
    Input("menu-home", "n_clicks"),
    Input("menu-agv-manager", "n_clicks"),
    Input("submenu-task-create", "n_clicks"),
    Input("submenu-task-list", "n_clicks"),
    Input("submenu-task-execute", "n_clicks"),
    prevent_initial_call=True,
)
def go_to_pages(create_click, setup_map_click, home_click, agv_mgr_click,
                task_create_click, task_list_click, task_execute_click):
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
    if trigger == "submenu-setup-map":
        return "/map-configure"

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
