import time

from dash import html

def layout(lang: str = "vi"):
    # ?v=<ts>: ép tải lại bản mới nhất mỗi lần vào trang (xem simulation_page.py)
    v = int(time.time())
    return html.Div(
        html.Iframe(
            src=f"/assets/task_execute.html?lang={lang}&v={v}",
            allow="fullscreen",
            style={
                "width": "100%",
                "height": "calc(100vh - 68px)",
                "border": "none",
                "borderRadius": "12px",
            }
        ),
        style={"width": "100%", "height": "100%", "padding": "4px 8px 4px 8px"}
    )
