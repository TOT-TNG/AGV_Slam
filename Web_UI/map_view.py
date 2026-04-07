from dash import html
from i18n import normalize_lang

# URL AGV map trên FastAPI
BASE_DASHBOARD_URL = "http://192.168.0.23:8000/AgvMap.html"

def layout(lang: str = "vi"):
    _ = normalize_lang(lang)
    return html.Div(
        html.Iframe(
            src=BASE_DASHBOARD_URL,
            style={"width": "100%", "height": "85vh", "border": "none"},
        )
    )
