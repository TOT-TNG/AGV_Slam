# login.py
import dash
from dash import html, dcc, Input, Output, State, callback
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import hashlib

# Tài khoản mẫu
HARD_CODED_USER = "admin"
HARD_CODED_PASS_HASH = hashlib.sha256("agv2025".encode()).hexdigest()

# Ngôn ngữ song ngữ
languages = {
    "en": {
        "title": "AGV Control System",
        "subtitle": "Connecting automation intelligently",
        "username": "Username",
        "password": "Password",
        "login": "Login",
        "copyright": "© Copyright by TOT-TNG",
        "contact": "Contact us: tot360.com.vn"
    },
    "vi": {
        "title": "Hệ thống điều khiển AGV",
        "subtitle": "Kết nối tự động hóa thông minh",
        "username": "Tên đăng nhập",
        "password": "Mật khẩu",
        "login": "Đăng nhập",
        "copyright": "© Bản quyền thuộc TOT-TNG",
        "contact": "Liên hệ: tot360.com.vn"
    }
}

# ================= LAYOUT =================
login_layout = html.Div([
    # Nền
    html.Div(className="bg-image"),

    # Icon chọn ngôn ngữ
    html.Div([
        html.Div([
            html.Img(
                src="https://img.icons8.com/ios-filled/50/ffffff/globe.png",
                id="lang-icon",
                className="",
                style={"width": "26px", "height": "26px", "cursor": "pointer"}
            ),
            html.Div(id="lang-menu", children=[
                html.Div("English", id="lang-en", n_clicks=0, className="lang-item"),
                html.Div("Tiếng Việt", id="lang-vi", n_clicks=0, className="lang-item")
            ], style={"display": "none"})
        ], id="lang-container")
    ], style={'position': 'absolute', 'top': '20px', 'right': '20px', 'zIndex': '1000'}),

    # Nội dung giữa
    html.Div(className="centered", children=[
        html.Img(src="/assets/icon.png", className="icon"),
        html.H1(id="login-title", className="title-white"),
        html.P(id="login-subtitle", className="subtitle"),

        html.Div(className="login-card mt-4", children=[
            dbc.Input(id="username-input", placeholder="", type="text", className="mb-3"),
            dbc.Input(id="password-input", placeholder="", type="password", className="mb-3", n_submit=0),
            dbc.Button(id="login-btn", color="primary", className="w-100"),
            html.Div(id="login-output", className="mt-2")
        ], style={"maxWidth": "360px", "margin": "16px auto"}),

        html.Div(id="copyright-text", style={
            'color': 'white',
            'fontSize': '14px',
            'opacity': '0.8',
            'fontFamily': 'Arial, sans-serif',
            'marginTop': '16px'
        }),
    ]),

    # Góc phải dưới: contact us
    html.Div(id="contact-text", style={
        'position': 'fixed',
        'bottom': '10px',
        'right': '20px',
        'color': 'white',
        'fontSize': '20px',
        'fontWeight': 'bold',
        'textShadow': '2px 2px 4px rgba(0,0,0,0.5)',
        'fontFamily': 'Arial, sans-serif',
        'zIndex': '999'
    }),

    # ✅ redirect để chuyển trang
    dcc.Location(id="redirect-home")
])


# ================= CALLBACKS =================

# Đổi ngôn ngữ
@callback(
    Output("login-title", "children"),
    Output("login-subtitle", "children"),
    Output("username-input", "placeholder"),
    Output("password-input", "placeholder"),
    Output("login-btn", "children"),
    Output("copyright-text", "children"),
    Output("contact-text", "children"),
    Input("lang-en", "n_clicks"),
    Input("lang-vi", "n_clicks")
)
def update_language(en_click, vi_click):
    ctx = dash.callback_context
    lang = "vi" if (ctx.triggered and ctx.triggered[0]['prop_id'].startswith("lang-vi")) else "en"
    lang_data = languages[lang]
    return (
        lang_data["title"], lang_data["subtitle"],
        lang_data["username"], lang_data["password"], lang_data["login"],
        lang_data["copyright"], lang_data["contact"]
    )


# Toggle menu ngôn ngữ
@callback(
    Output("lang-menu", "style"),
    Input("lang-icon", "n_clicks"),
    State("lang-menu", "style"),
    prevent_initial_call=True
)
def toggle_lang_menu(n_clicks, style):
    if not style or style.get("display") == "none":
        return {"display": "block"}
    return {"display": "none"}


# Cho phép nhấn Enter để login
@callback(
    Output("login-btn", "n_clicks"),
    Input("password-input", "n_submit"),
    State("login-btn", "n_clicks"),
    prevent_initial_call=True
)
def enter_login(n_submit, n_clicks):
    if n_submit:
        return (n_clicks or 0) + 1
    raise PreventUpdate


# ✅ Đăng nhập & redirect sang /home
@callback(
    Output("login-output", "children"),
    Output("redirect-home", "href"),
    Input("login-btn", "n_clicks"),
    State("username-input", "value"),
    State("password-input", "value"),
    prevent_initial_call=True
)
def do_login(n_clicks, username, password):
    if not n_clicks:
        raise PreventUpdate

    if username and password:
        if username == HARD_CODED_USER and hashlib.sha256(password.encode()).hexdigest() == HARD_CODED_PASS_HASH:
            # Đăng nhập đúng → chuyển đến /home
            return dbc.Alert("Login successful!", color="success", dismissable=True), "/home"
        else:
            return dbc.Alert("Wrong username or password!", color="danger", dismissable=True), dash.no_update
    return "", dash.no_update
