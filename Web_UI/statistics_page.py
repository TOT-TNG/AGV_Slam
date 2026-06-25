from dash import html

def layout(lang: str = "vi"):
    return html.Div(
        html.Iframe(
            src=f"/assets/statistics.html?lang={lang}",
            style={"width": "100%", "height": "calc(100vh - 68px)", "border": "none"},
        ),
        style={"width": "100%", "height": "100%", "padding": "4px 8px"},
    )
