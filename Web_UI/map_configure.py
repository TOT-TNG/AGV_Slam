from dash import html

def map_configure_layout():
    return html.Div(
        [
            html.Iframe(
                src="/assets/MapConfigure.html",
                style={
                    "width": "100%",
                    "height": "calc(100vh - 120px)",
                    "border": "none",
                    "borderRadius": "12px",
                    "backgroundColor": "transparent"
                }
            )
        ],
        style={
            "width": "100%",
            "height": "100%",
            "padding": "12px"
        }
    )