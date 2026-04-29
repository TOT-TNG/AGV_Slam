<<<<<<< HEAD
from dash import Dash, html, dcc, Input, Output, State, no_update
import dash_bootstrap_components as dbc
import dash

=======
import dash
from dash import Dash, html, dcc, Input, Output, State, no_update
import dash_bootstrap_components as dbc
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
from i18n import DEFAULT_LANG, normalize_lang
from login import login_layout
from home import home_layout, make_sidebar, make_topbar
from create_map import layout as create_map_layout
from map_view import layout as map_view_layout
from agv_manager import layout as agv_manager_layout
from task_create import layout as task_create_layout
from task_list import layout as task_list_layout
<<<<<<< HEAD
=======
from map_configure import map_configure_layout

>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574

# Dash app
app = Dash(
    __name__,
    suppress_callback_exceptions=True,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
<<<<<<< HEAD
        # ✅ cần cho icon globe/caret trong topbar (bi bi-...)
=======
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css",
    ],
)
server = app.server
app.title = "TOT ACS"

<<<<<<< HEAD
=======

>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
# ==== ROUTING LAYOUT: shell cố định cho các trang nội bộ, login tách riêng ==== #
app.layout = html.Div(
    [
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="lang-menu-open", data=False, storage_type="memory"),
<<<<<<< HEAD

        # global language store (local: giữ sau khi refresh)
        dcc.Store(id="lang-store", data=DEFAULT_LANG, storage_type="local"),

        # ✅ Toast thông báo reload (ổn định hơn ConfirmDialog)
=======
        dcc.Store(id="lang-store", data=DEFAULT_LANG, storage_type="local"),

>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
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
<<<<<<< HEAD
        # Assistant alert toast (global)
=======

>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
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
            data={"map_open": False, "task_open": False, "map_clicks": 0, "task_clicks": 0},
            storage_type="session",
        ),
<<<<<<< HEAD
        html.Div(id="page-wrapper"),
        # Global language menu panel (teleport)
        html.Div(
            id="lang-menu-panel",
            children=[
                html.Div("VIE", id="lang-item-vi", n_clicks=0, style={"padding": "10px 14px", "cursor": "pointer"}),
                html.Div("ENG", id="lang-item-en", n_clicks=0, style={"padding": "10px 14px", "cursor": "pointer"}),
=======

        html.Div(id="page-wrapper"),

        html.Div(
            id="lang-menu-panel",
            children=[
                html.Div(
                    "VIE",
                    id="lang-item-vi",
                    n_clicks=0,
                    style={"padding": "10px 14px", "cursor": "pointer"},
                ),
                html.Div(
                    "ENG",
                    id="lang-item-en",
                    n_clicks=0,
                    style={"padding": "10px 14px", "cursor": "pointer"},
                ),
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
            ],
            style={
                "display": "none",
                "position": "fixed",
                "top": "60px",
                "left": "0px",
                "minWidth": "160px",
                "background": "rgba(30, 41, 59, 0.98)",
                "border": "1px solid rgba(255,255,255,0.12)",
                "borderRadius": "12px",
                "boxShadow": "0 10px 28px rgba(0,0,0,0.35)",
<<<<<<< HEAD
                "zIndex": "2147483647",   # MAX-ish
                "overflow": "hidden",
            },
        ),
        '''dcc.Store(id="lang-menu-open", data=False, storage_type="memory"),'''
=======
                "zIndex": "2147483647",
                "overflow": "hidden",
            },
        ),
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
    ]
)


def _route_content(pathname, lang: str):
<<<<<<< HEAD
    # NOTE: all pages below are factories: layout(lang)
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
=======
    if pathname in ["/home", "/home/"]:
        return home_layout(lang)

    if pathname in ["/create-map", "/home/create-map"]:
        return create_map_layout(lang)

    if pathname in ["/map-configure", "/home/map-configure"]:
        return map_configure_layout()

    if pathname in ["/map-view", "/home/map-view"]:
        return map_view_layout(lang)

    if pathname in ["/agv-manager", "/home/agv-manager"]:
        return agv_manager_layout(lang)

    if pathname in ["/task-manager", "/home/task-manager", "/task-list"]:
        return task_list_layout(lang)

>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
    if pathname in ["/task-create", "/home/task-create"]:
        return task_create_layout(lang)

    return html.Div(
        html.H3(
            "404 - Page Not Found",
            style={"color": "white", "textAlign": "center", "marginTop": "50px"},
        )
    )


# ==== PAGE RENDERING (pathname + lang) ==== #
@app.callback(
    Output("page-wrapper", "children"),
    Input("url", "pathname"),
    Input("lang-store", "data"),
)
def display_page(pathname, lang):
    lang = normalize_lang(lang)

    if pathname in ["/", "/login"]:
<<<<<<< HEAD
        # Trang login giữ nguyên, không kèm sidebar/topbar/nền
        return login_layout

    content = _route_content(pathname, lang)
=======
        return login_layout

    content = _route_content(pathname, lang)

>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
    return html.Div(
        [
            html.Div(className="background-div"),
            make_sidebar(lang),
            html.Div(
                [
                    make_topbar(lang),
                    html.Div(content, className="page-body"),
                ],
                className="main-panel",
            ),
        ]
    )


# ==== LANGUAGE SWITCH (menu item click -> store + show toast) ==== #
@app.callback(
    Output("lang-store", "data", allow_duplicate=True),
    Output("lang-toast", "is_open"),
    Output("lang-toast", "header"),
    Output("lang-toast-msg", "children"),
    Input("lang-item-vi", "n_clicks"),
    Input("lang-item-en", "n_clicks"),
    State("lang-store", "data"),
    prevent_initial_call=True,
)
def set_language_from_menu(n_vi, n_en, current):
    trig = dash.callback_context.triggered_id

<<<<<<< HEAD
    # ✅ Chỉ xử lý khi click THẬT (n_clicks > 0)
=======
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
    if trig == "lang-item-vi":
        if not n_vi or n_vi < 1:
            raise dash.exceptions.PreventUpdate
        new_lang = "vi"
    elif trig == "lang-item-en":
        if not n_en or n_en < 1:
            raise dash.exceptions.PreventUpdate
        new_lang = "en"
    else:
        raise dash.exceptions.PreventUpdate

    new_lang = normalize_lang(new_lang)
    current = normalize_lang(current)

    if new_lang == current:
        raise dash.exceptions.PreventUpdate

    if new_lang == "vi":
        header = "Đổi ngôn ngữ"
        msg = "Đã đổi sang Tiếng Việt. Vui lòng tải lại trang (F5 / Ctrl+R) để đảm bảo toàn bộ giao diện cập nhật đúng."
    else:
        header = "Language changed"
        msg = "Switched to English. Please reload the page (F5 / Ctrl+R) to ensure the entire UI updates correctly."

    return new_lang, True, header, msg

<<<<<<< HEAD
=======

>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
@app.callback(
    Output("lang-menu-panel", "style"),
    Output("lang-menu-open", "data"),
    Input("lang-toggle", "n_clicks"),
    Input("lang-item-vi", "n_clicks"),
    Input("lang-item-en", "n_clicks"),
    State("lang-menu-open", "data"),
    prevent_initial_call=True,
)
def toggle_lang_menu(n_toggle, n_vi, n_en, is_open):
    trig = dash.callback_context.triggered_id
    is_open = bool(is_open)

<<<<<<< HEAD
    # ✅ Guard: tránh “kích ảo” khi re-render (n_clicks về 0)
=======
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
    if trig == "lang-toggle" and (not n_toggle or n_toggle < 1):
        raise dash.exceptions.PreventUpdate
    if trig == "lang-item-vi" and (not n_vi or n_vi < 1):
        raise dash.exceptions.PreventUpdate
    if trig == "lang-item-en" and (not n_en or n_en < 1):
        raise dash.exceptions.PreventUpdate

    if trig == "lang-toggle":
        is_open = not is_open
    elif trig in ("lang-item-vi", "lang-item-en"):
        is_open = False
    else:
        raise dash.exceptions.PreventUpdate

    style = {
        "display": "block" if is_open else "none",
        "position": "absolute",
        "top": "calc(100% + 8px)",
        "right": "0",
        "minWidth": "160px",
        "background": "rgba(30, 41, 59, 0.98)",
        "border": "1px solid rgba(255,255,255,0.12)",
        "borderRadius": "12px",
        "boxShadow": "0 10px 28px rgba(0,0,0,0.35)",
<<<<<<< HEAD
        "zIndex": "20000",        # ✅ cực cao để nổi trên mọi panel
        "overflow": "hidden",
    }
    return style, is_open



if __name__ == "__main__":
    app.run(host="192.168.88.253", port=8050, debug=True)
=======
        "zIndex": "20000",
        "overflow": "hidden",
    }

    return style, is_open


if __name__ == "__main__":
    app.run(host="192.168.0.23", port=8050, debug=True, dev_tools_ui=False)
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
