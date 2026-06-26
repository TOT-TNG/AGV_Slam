from dash import html
from i18n import normalize_lang

# URL AGV map trên FastAPI
BASE_DASHBOARD_URL = "http://192.168.0.86:8000/AgvMap.html"

def layout(lang: str = "vi"):
    _ = normalize_lang(lang)
    return html.Div(
        html.Iframe(
            src=BASE_DASHBOARD_URL,
            style={"width": "100%", "height": "calc(100vh - 68px)", "border": "none", "borderRadius": "12px"},
        ),
        style={"width": "100%", "height": "100%", "padding": "4px 8px 4px 8px"}
    )
