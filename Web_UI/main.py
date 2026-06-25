import dash
from dash import Dash, html, dcc, Input, Output, State, no_update
import dash_bootstrap_components as dbc

from i18n import DEFAULT_LANG, normalize_lang
from login import login_layout
from home import (home_layout, make_sidebar, make_topbar,
                  settings_language_layout, settings_broker_layout)
from create_map import layout as create_map_layout
from map_view import layout as map_view_layout
from agv_manager import layout as agv_manager_layout
from task_create import layout as task_create_layout
from task_list import layout as task_list_layout
from task_execute import layout as task_execute_layout
from journal_history import layout as journal_history_layout
from journal_logs import layout as journal_logs_layout
from statistics_page import layout as statistics_layout


def _integration_iframe_layout(lang="vi"):
    return html.Div(
        html.Iframe(
            src=f"/assets/integration.html?lang={lang}",
            style={"width": "100%", "height": "calc(100vh - 64px)",
                   "border": "none", "display": "block"},
        ),
        style={"height": "100%"},
    )


# Dash app
app = Dash(
    __name__,
    suppress_callback_exceptions=True,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css",
    ],
)
server = app.server
app.title = "TOT ACS"


app.layout = html.Div(
    [
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="lang-store", data=DEFAULT_LANG, storage_type="local"),
        dbc.Toast(
            id="lang-toast",
            header="",
            children=html.Div(id="lang-toast-msg"),
            is_open=False,
            dismissable=True,
            duration=None,
            style={
                "position": "fixed",
                "top": "80px",
                "right": "24px",
                "width": "420px",
                "zIndex": 3000,
            },
        ),
        html.Div(
            id="assistant-toast",
            className="assistant-toast idle",
            children=[
                html.Div("AI", className="assistant-avatar"),
                html.Div(
                    [
                        html.Div("Tro ly ao", id="assistant-title", className="assistant-title"),
                        html.Div("", id="assistant-message", className="assistant-message"),
                    ],
                    className="assistant-body",
                ),
                html.Button("x", id="assistant-close", className="assistant-close", n_clicks=0),
            ],
        ),
        dcc.Store(
            id="submenu-store",
            data={"map_open": False, "task_open": False},
            storage_type="memory",
        ),
        html.Div(id="page-wrapper"),
    ]
)


def _route_content(pathname, lang: str):
    if pathname in ["/home", "/home/"]:
        return home_layout(lang)
    if pathname in ["/create-map", "/home/create-map"]:
        return create_map_layout(lang)
    if pathname in ["/map-view", "/home/map-view"]:
        return map_view_layout(lang)
    if pathname in ["/agv-manager", "/home/agv-manager"]:
        return agv_manager_layout(lang)
    if pathname in ["/task-manager", "/home/task-manager", "/task-list"]:
        return task_list_layout(lang)
    if pathname in ["/task-create", "/home/task-create"]:
        return task_create_layout(lang)
    if pathname in ["/task-execute", "/home/task-execute"]:
        return task_execute_layout(lang)
    if pathname in ["/journal-history", "/home/journal-history"]:
        return journal_history_layout(lang)
    if pathname in ["/journal-logs", "/home/journal-logs"]:
        return journal_logs_layout(lang)
    if pathname in ["/statistics", "/home/statistics"]:
        return statistics_layout(lang)
    if pathname in ["/integration", "/home/integration"]:
        return _integration_iframe_layout(lang)
    if pathname in ["/settings-language", "/home/settings-language"]:
        return settings_language_layout(lang)
    if pathname in ["/settings-broker", "/home/settings-broker"]:
        return settings_broker_layout(lang)

    return html.Div(
        html.H3(
            "404 - Page Not Found",
            style={"color": "white", "textAlign": "center", "marginTop": "50px"},
        )
    )


@app.callback(
    Output("page-wrapper", "children"),
    Input("url", "pathname"),
    Input("lang-store", "data"),
)
def display_page(pathname, lang):
    lang = normalize_lang(lang)

    if pathname in ["/", "/login"]:
        return login_layout

    content = _route_content(pathname, lang)

    return html.Div(
        [
            html.Div(className="background-div"),
            make_sidebar(lang, pathname),
            html.Div(
                [
                    make_topbar(lang),
                    html.Div(content, className="page-body"),
                ],
                className="main-panel",
            ),
        ]
    )


@app.callback(
    Output("lang-store", "data", allow_duplicate=True),
    Output("lang-toast", "is_open"),
    Output("lang-toast", "header"),
    Output("lang-toast-msg", "children"),
    Input("settings-lang-vi", "n_clicks"),
    Input("settings-lang-en", "n_clicks"),
    State("lang-store", "data"),
    prevent_initial_call=True,
)
def set_language_from_settings(n_vi, n_en, current):
    trig = dash.callback_context.triggered_id

    if trig == "settings-lang-vi":
        if not n_vi or n_vi < 1:
            raise dash.exceptions.PreventUpdate
        new_lang = "vi"
    elif trig == "settings-lang-en":
        if not n_en or n_en < 1:
            raise dash.exceptions.PreventUpdate
        new_lang = "en"
    else:
        raise dash.exceptions.PreventUpdate

    new_lang = normalize_lang(new_lang)
    current  = normalize_lang(current)

    if new_lang == current:
        raise dash.exceptions.PreventUpdate

    if new_lang == "vi":
        header = "Đổi ngôn ngữ"
        msg = "Đã đổi sang Tiếng Việt. Vui lòng tải lại trang (F5 / Ctrl+R) để đảm bảo toàn bộ giao diện cập nhật đúng."
    else:
        header = "Language changed"
        msg = "Switched to English. Please reload (F5 / Ctrl+R) to apply the new language across the UI."

    return new_lang, True, header, msg


if __name__ == "__main__":
    app.run(host="192.168.0.89", port=8050, debug=True, dev_tools_ui=False)
