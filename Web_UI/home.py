from dash import html, dcc, Input, Output, State, callback, no_update
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
import dash

from i18n import t, normalize_lang

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
def make_sidebar(lang: str):
    lang = normalize_lang(lang)
    return html.Div(
        [
            html.Div(t(lang, "app.title", "TOT ACS"), className="menu-logo"),
            html.Div(
                [
                    html.Div(
                        [html.I(className="bi bi-house-door me-2"), html.Span(t(lang, "menu.home", "Home"))],
                        className="menu-item",
                        id="menu-home",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [html.I(className="bi bi-map me-2"), html.Span(t(lang, "menu.map", "Map"))],
                                className="menu-item",
                                id="menu-map",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        t(lang, "menu.map.create", "Create Map"),
                                        id="submenu-create-map",
                                        className="submenu-item",
                                    ),
                                    html.Div(
                                        t(lang, "menu.map.configure", "Map Configure"),
                                        id="submenu-setup-map",
                                        className="submenu-item",
                                    ),
                                    html.A(
                                        t(lang, "menu.map.agvmap", "AGV Map"),
                                        href="http://192.168.0.23:8000/AgvMap.html",
                                        target="_blank",
                                        className="submenu-item",
                                        style={"textDecoration": "none", "color": "inherit"},
                                    ),
                                ],
                                id="submenu-map",
                                className="submenu",
                                style={"display": "none"},
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            html.Div(
                                [html.I(className="bi bi-list-task me-2"), html.Span(t(lang, "menu.task", "Task Manager"))],
                                className="menu-item",
                                id="menu-task",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        t(lang, "menu.task.create", "Create Task"),
                                        id="submenu-task-create",
                                        className="submenu-item",
                                    ),
                                    html.Div(
                                        t(lang, "menu.task.list", "Task List"),
                                        id="submenu-task-list",
                                        className="submenu-item",
                                    ),
                                ],
                                id="submenu-task",
                                className="submenu",
                                style={"display": "none"},
                            ),
                        ]
                    ),
                    html.Div(
                        [html.I(className="bi bi-cpu me-2"), html.Span(t(lang, "menu.agv", "AGV Manager"))],
                        className="menu-item",
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
# - chỉ giữ nút toggle ngôn ngữ
# - panel ngôn ngữ thật đã nằm ở main.py để tránh trùng id
def make_topbar(lang: str):
    lang = normalize_lang(lang)
    abbr = "VIE" if lang == "vi" else "ENG"

    return html.Div(
        [
            html.Div(t(lang, "topbar.title", "AGV Control System (ACS)"), className="topbar-title"),
            html.Div(
                [
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


@callback(
    Output("submenu-store", "data", allow_duplicate=True),
    Input("menu-map", "n_clicks"),
    Input("menu-task", "n_clicks"),
    State("submenu-store", "data"),
    prevent_initial_call=True,
)
def toggle_submenus(map_click, task_click, store):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate

    trigger = ctx.triggered[0]["prop_id"].split(".")[0]
    store = store or {"map_open": False, "task_open": False, "map_clicks": -1, "task_clicks": -1}

    prev_map_clicks = store.get("map_clicks", -1)
    prev_task_clicks = store.get("task_clicks", -1)
    map_clicks = map_click if map_click is not None else prev_map_clicks
    task_clicks = task_click if task_click is not None else prev_task_clicks

    changed_map = trigger == "menu-map" and map_click is not None and map_clicks != prev_map_clicks
    changed_task = trigger == "menu-task" and task_click is not None and task_clicks != prev_task_clicks

    if not (changed_map or changed_task):
        raise dash.exceptions.PreventUpdate

    map_open = store.get("map_open", False)
    task_open = store.get("task_open", False)

    if changed_map:
        map_open = not map_open
        task_open = False

    if changed_task:
        task_open = not task_open
        map_open = False

    new_store = {
        "map_open": map_open,
        "task_open": task_open,
        "map_clicks": map_clicks,
        "task_clicks": task_clicks,
    }
    return new_store


@callback(
    Output("submenu-map", "style"),
    Input("submenu-store", "data"),
)
def apply_map_submenu(data):
    open_state = (data or {}).get("map_open", False)
    return {"display": "block", "marginLeft": "32px"} if open_state else {"display": "none"}


@callback(
    Output("submenu-task", "style"),
    Input("submenu-store", "data"),
)
def apply_task_submenu(data):
    open_state = (data or {}).get("task_open", False)
    return {"display": "block", "marginLeft": "32px"} if open_state else {"display": "none"}


@callback(
    Output("url", "pathname", allow_duplicate=True),
    Input("submenu-create-map", "n_clicks"),
    Input("submenu-setup-map", "n_clicks"),
    Input("menu-home", "n_clicks"),
    Input("menu-agv-manager", "n_clicks"),
    Input("submenu-task-create", "n_clicks"),
    Input("submenu-task-list", "n_clicks"),
    prevent_initial_call=True,
)
def go_to_pages(create_click, setup_map_click, home_click, agv_mgr_click, task_create_click, task_list_click):
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
    if trigger == "submenu-create-map":
        return "/create-map"
    if trigger == "submenu-setup-map":
        return "/map-configure"

    return no_update


# Backward compatibility
sidebar = make_sidebar("vi")
topbar = make_topbar("vi")