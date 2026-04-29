from dash import html
from home import sidebar, topbar
from i18n import t, normalize_lang

def layout(lang: str = "vi"):
    lang = normalize_lang(lang)

    # Nếu home.py đang dùng wrapper sidebar/topbar default (Cách 1) thì vẫn OK.
    # Nếu Sếp muốn sidebar/topbar đổi theo lang cho đúng 100%, thì main.py sẽ render khung,
    # còn page chỉ cần content.
    return html.Div(
        [
            sidebar,
            html.Div(
                [
                    topbar,
                    html.H2(t(lang, "task_list.title", "Task List"), style={"color": "white"}),
                    html.Div(
                        t(lang, "task_list.desc", "Hiển thị danh sách task (đang phát triển)."),
                        style={"color": "rgba(255,255,255,0.7)", "marginTop": "8px"},
                    ),
                ],
                className="content",
            ),
        ],
        className="layout",
    )
