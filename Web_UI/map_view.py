from dash import html
from i18n import normalize_lang

# URL AGV map trên FastAPI
<<<<<<< HEAD
BASE_DASHBOARD_URL = "http://192.168.88.253:8000/AgvMap.html"
=======
BASE_DASHBOARD_URL = "http://192.168.0.23:8000/AgvMap.html"
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574

def layout(lang: str = "vi"):
    _ = normalize_lang(lang)
    return html.Div(
        html.Iframe(
            src=BASE_DASHBOARD_URL,
            style={"width": "100%", "height": "85vh", "border": "none"},
        )
    )
