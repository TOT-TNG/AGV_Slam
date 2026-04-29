from dash import html, dcc, Input, Output, callback, clientside_callback, ClientsideFunction, no_update
import dash_bootstrap_components as dbc
def layout(lang: str = "vi"):
    from i18n import t, normalize_lang
    lang = normalize_lang(lang)
    return html.Div([
    dcc.Store(id="map-store"),
    html.Div(id="dummy-output", style={"display": "none"}),
    html.Div([

            # === TOOLBOX TOGGLE BUTTON ===
            html.Div([
                html.Div("←", id="toggle-toolbox-btn", n_clicks=0, className="toolbox-toggle")
            ], className="toolbox-toggle-container"),

            # === TOOLBOX PANEL ===
            html.Div([
                html.H5(t(lang, "create_map.toolbox", "Toolbox"), className="fw-bold text-primary mb-3"),
                html.Div([
                    html.Div(className="tool-icon node-icon"),
                    html.Div(t(lang, "create_map.node", "Node"), className="tool-label")
                ], id="add-node", className="tool-item"),
                html.Hr(),
            ], id="toolbox-panel", className="toolbox-panel"),

            # === MAP DESIGN AREA ===
            html.Div(
                id="map-design-area",
                className="map-design-area",
                style={
                    "position": "relative",
                    "overflow": "visible",
                    "height": "calc(100vh - 120px)",
                    "background": "white",
                    "borderRadius": "12px",
                    "margin": "20px",
                    "cursor": "grab",
                    "userSelect": "none"
                },
                children=[
                    # CONTAINER CHÍNH
                    html.Div(
                        id="map-container",
                        style={
                            "position": "absolute",
                            "top": "0%", "left": "0%",
                            "width": "3000px",
                            "height": "2000px",
                            "transformOrigin": "0 0",
                            "pointerEvents": "none"
                        },
                        children=[
                            html.Div(id="map-canvas", style={"pointerEvents": "auto"}),
                            html.Div(id="edge-layer", style={"pointerEvents": "auto"})
                        ]
                    ),

                    # HIỂN THỊ ZOOM LEVEL
                    html.Div(
                        "Zoom: 100%",
                        id="zoom-level",
                        style={
                            "position": "absolute",
                            "bottom": "12px", "right": "12px",
                            "background": "rgba(0,0,0,0.8)", "color": "white",
                            "padding": "8px 12px", "borderRadius": "8px",
                            "fontWeight": "bold", "zIndex": 1000,
                            "pointerEvents": "none"
                        }
                    )
                ]
            ),

            # === NODE PROPERTIES PANEL ===
            html.Div(
                id="properties-panel",
                className="toolbox-panel bg-white shadow-lg",
                style={
                    "position": "fixed", "right": "-280px", "top": "70px",
                    "width": "280px", "height": "calc(100vh - 90px)",
                    "zIndex": 1000, "transition": "right 0.35s ease",
                    "display": "flex", "flexDirection": "column",
                    "borderRadius": "0 0 0 16px", "overflow": "hidden"
                },
                children=[
                    html.Div([
                        html.H5(t(lang, "create_map.properties", "Properties"), className="fw-bold text-primary mb-2 px-3 pt-3"),
                        html.Div(t(lang, "create_map.node", "Node"), id="prop-target", className="text-muted small px-3 mb-1"),
                        html.Hr(className="mx-3")
                    ]),

                    html.Div([
                        html.Div([
                            html.Label("Name", className="form-label text-dark px-3"),
                            dcc.Input(id="prop-name", type="text", className="form-control form-control-sm mx-3 mb-2", placeholder="Tên..."),

                            html.Label("X", className="form-label text-dark px-3 mt-2"),
                            dcc.Input(id="prop-x", type="number", className="form-control form-control-sm mx-3 mb-2"),

                            html.Label("Y", className="form-label text-dark px-3 mt-2"),
                            dcc.Input(id="prop-y", type="number", className="form-control form-control-sm mx-3 mb-2"),

                            html.Label("Quay (độ)", className="form-label text-dark px-3 mt-2"),
                            dcc.Dropdown(
                                id="prop-rotate",
                                options=[{"label": f"{i}°", "value": i} for i in range(0, 361, 45)],
                                className="form-select form-select-sm mx-3 mb-2"
                            ),
                            html.Label("Chức năng", className="form-label text-dark px-3 mt-2"),
                            dcc.Dropdown(
                                id="prop-function",
                                options=[
                                    {"label": "Trạm sạc", "value": "charging"},
                                    {"label": "Điểm chờ", "value": "wait"},
                                    {"label": "Điểm giao nhận", "value": "pickup"},
                                    {"label": "Bình thường", "value": "normal"}
                                ],
                                className="form-select form-select-sm mx-3 mb-2"
                            ),
                            html.Label("Tốc độ (m/s)", className="form-label text-dark px-3 mt-2"),
                            dcc.Input(id="prop-speed", type="number", min=0.1, max=2.0, step=0.1, value=0.5,
                                    className="form-control form-control-sm mx-3 mb-3"),

                            html.Div([
                                html.Label("Lidar", className="form-label text-dark mb-2"),
                                html.Div([
                                    dbc.Switch(id="prop-lidar", label="", value=True, className="float-end")
                                ], className="d-flex align-items-center")
                            ], className="px-3 mb-3")
                        ])
                    ], style={
                        "flex": 1,
                        "overflowY": "auto",
                        "paddingBottom": "80px"
                    }),

                    html.Div([
                        html.Div([
                            html.Button(t(lang, "create_map.save", "Save"), id="prop-save", className="btn btn-success btn-sm px-4"),
                            html.Button(t(lang, "create_map.close", "Close"), id="prop-close", className="btn btn-outline-secondary btn-sm px-4 ms-2")
                        ], className="d-flex justify-content-center")
                    ], className="border-top bg-white py-3", style={
                        "position": "sticky", "bottom": 0, "zIndex": 10,
                        "boxShadow": "0 -2px 10px rgba(0,0,0,0.05)"
                    })
                ]
            ),

            # === EDGE PROPERTIES PANEL ===
            html.Div(
                id="edge-properties-panel",
                className="toolbox-panel bg-white shadow-lg",
                style={
                    "position": "fixed", "right": "-280px", "top": "70px",
                    "width": "280px", "height": "calc(100vh - 90px)",
                    "zIndex": 1001, "transition": "right 0.35s ease",
                    "display": "flex", "flexDirection": "column",
                    "borderRadius": "0 0 0 16px", "overflow": "hidden"
                },
                children=[
                    html.Div([
                        html.H5(t(lang, "create_map.properties", "Properties"), className="fw-bold text-primary mb-2 px-3 pt-3"),
                        html.Div("Edge", id="edge-target", className="text-muted small px-3 mb-1"),
                        html.Hr(className="mx-3")
                    ]),

                    html.Div([
                        html.Label("Di chuyển", className="form-label text-dark px-3"),
                        dbc.Select(
                            id="edge-direction",
                            options=[
                                {"label": "2 chiều", "value": "both"},
                                {"label": "Chiều tiến", "value": "forward"},
                                {"label": "Chiều lùi", "value": "backward"},
                                {"label": "Cấm chạy", "value": "blocked"}
                            ],
                            value="both",
                            className="form-select form-select-sm mx-3 mb-2"
                        ),

                        html.Div(id="blocked-agvs-container", children=[
                            html.Label("Cấm AGV", className="form-label text-dark px-3 mt-2"),
                            dbc.Checklist(
                                options=[{"label": f"AGV{i:02d}", "value": f"AGV{i:02d}"} for i in range(1, 9)],
                                value=[],
                                id="edge-blocked-agvs",
                                inline=True,
                                className="px-3"
                            )
                        ], style={"display": "none"}),

                        html.Label("Tốc độ (m/s)", className="form-label text-dark px-3 mt-3"),
                        dcc.Input(
                            id="edge-speed",
                            type="number",
                            min=0, max=2, step=0.1,
                            value=0.5,
                            className="form-control form-control-sm mx-3 mb-3"
                        ),

                        html.Div([
                            html.Label("Lidar", className="form-label text-dark mb-2"),
                            html.Div([
                                dbc.Switch(id="edge-lidar", label="", value=True, className="float-end")
                            ], className="d-flex align-items-center")
                        ], className="px-3 mb-4"),
                    ], style={"flex": 1, "overflowY": "auto", "paddingBottom": "80px"}),

                    html.Div([
                        html.Div([
                            html.Button(t(lang, "create_map.save", "Save"), id="edge-save", className="btn btn-success btn-sm px-4"),
                            html.Button(t(lang, "create_map.close", "Close"), id="edge-close", className="btn btn-outline-secondary btn-sm px-4 ms-2")
                        ], className="d-flex justify-content-center")
                    ], className="border-top bg-white py-3", style={
                        "position": "sticky", "bottom": 0, "zIndex": 10,
                        "boxShadow": "0 -2px 10px rgba(0,0,0,0.05)"
                    })
                ]
            )

        ], className="map-main-container")
    ], className="main-panel")



# === TOOLBOX BUTTON CALLBACK ===
@callback(
    Output("toolbox-panel", "className"),
    Output("toggle-toolbox-btn", "children"),
    Input("toggle-toolbox-btn", "n_clicks"),
    prevent_initial_call=True
)
def toggle_toolbox(n):
    return ("toolbox-panel open", "→") if n % 2 else ("toolbox-panel", "←")


# N?t Home: quay v? m?n h?nh home
# === CLIENTSIDE INIT ===
clientside_callback(
    ClientsideFunction(namespace="clientside", function_name="init_map"),
    Output("dummy-output", "children"),
    Input("map-design-area", "id")
)
