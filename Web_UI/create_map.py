from dash import html


def layout(lang: str = "vi"):
    return html.Div(
        html.Iframe(
            src=f"/assets/map_editor.html?lang={lang}",
            style={
                "width": "100%",
                "height": "calc(100vh - 68px)",
                "border": "none",
                "display": "block",
            }
        ),
        style={"width": "100%", "height": "100%", "padding": "4px 8px 4px 8px"}
    )
