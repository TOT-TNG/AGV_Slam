from dash import html, dcc, callback, Output, Input, State, no_update, callback_context
import dash_bootstrap_components as dbc
import json

from i18n import t, normalize_lang

# ===== Templates (panel trái) =====
# Giữ nguyên KEY + steps logic; title/steps sẽ dịch theo lang khi render page
TEMPLATES_BASE = [
    {
        "key": "MOVE_TO_POSE",
        "title_en": "Transfer Goods",
        "title_vi": "Transfer Goods",
        "action_type": "MOVE_TO_POSE",
        "config": {"name": ""},
    },
    {
        "key": "PICKUP",
        "title_en": "Pickup",
        "title_vi": "Pickup",
        "action_type": "PICKUP",
        "config": {},
    },
    {
        "key": "DROP",
        "title_en": "Drop",
        "title_vi": "Drop",
        "action_type": "DROP",
        "config": {},
    },
]
def _templates_for_lang(lang: str):
    lang = normalize_lang(lang)
    out = []
    for tpl in TEMPLATES_BASE:
        out.append({
            "key": tpl["key"],
            "title": tpl["title_en"] if lang == "en" else tpl["title_vi"],
            "action_type": tpl["action_type"],
            "config": tpl["config"],
        })
    return out

def _task_tile(tpl, active=False):
    payload = json.dumps(tpl, ensure_ascii=False)
    return html.Div(
        [
            html.Div(className="task-icon me-2"),
            html.Div(tpl["title"], className="task-label"),
        ],
        className=f"task-tile{' active' if active else ''}",
        **{
            "data-key": tpl["key"],
            "data-command": tpl["title"],
            "data-payload": payload,
        },
    )

def layout(lang: str = "vi"):
    lang = normalize_lang(lang)
    templates = _templates_for_lang(lang)

    # i18n cho JS node UI (tooltip remove, fallback title)
    wf_i18n = {
        "remove": t(lang, "wf.remove", "Remove"),
        "task_group": t(lang, "wf.task_group", "Task Group"),
    }

    return html.Div(
        [
            # Stores JS -> Dash
            dcc.Store(id="wf-state", data={"nodes": [], "edges": [], "selection": None}),
            dcc.Store(id="wf-selection", data=None),

            dbc.Modal(
                [
                    dbc.ModalHeader(dbc.ModalTitle(t(lang, "task_create.modal.title", "Save Workflow"))),
                    dbc.ModalBody(
                        [
                            dbc.Label(t(lang, "task_create.modal.name", "Workflow name")),
                            dbc.Input(
                                id="wf-name",
                                placeholder=t(lang, "task_create.modal.placeholder", "Enter workflow name..."),
                                type="text",
                                value="",
                            ),
                            html.Div(id="wf-save-error", className="mt-2"),
                        ]
                    ),
                    dbc.ModalFooter(
                        [
                            dbc.Button(t(lang, "task_create.cancel", "Cancel"), id="btn-save-workflow-cancel", color="secondary", n_clicks=0),
                            dbc.Button(t(lang, "task_create.save", "Save"), id="btn-save-workflow-confirm", color="primary", n_clicks=0),
                        ]
                    ),
                ],
                id="modal-save-workflow",
                is_open=False,
            ),

            # Store config per node
            dcc.Store(id="wf-config", data={}),

            # bootstrap templates for JS (wf_reactflow.js đọc window.__WF_TEMPLATES)
            html.Script(
                "window.__WF_TEMPLATES = " + json.dumps(templates, ensure_ascii=False) + ";"
                + "window.__WF_LANG = " + json.dumps(lang, ensure_ascii=False) + ";"
                + "window.__WF_I18N = " + json.dumps(wf_i18n, ensure_ascii=False) + ";",
            ),

            # LEFT
            html.Div(
                [
                    html.Div(t(lang, "task_create.left", "Task Group List"), className="panel-title"),
                    html.Div(
                        [_task_tile(tpl, active=(i == 0)) for i, tpl in enumerate(templates)],
                        className="task-list",
                        id="task-list-container",
                    ),
                ],
                className="task-panel left-panel",
            ),

            # CENTER
            html.Div(
                [
                    html.Div(t(lang, "task_create.center", "Workflow"), className="panel-title"),
                    html.Div(
                        [
                            dbc.Button(t(lang, "task_create.save_workflow", "Save Workflow"), id="btn-save-workflow-open", color="success", size="sm", n_clicks=0),
                        ],
                        style={"display": "flex", "justifyContent": "flex-end", "marginBottom": "8px"},
                    ),
                    html.Div(
                        html.Div(id="wf-root"),
                        className="wf-scroll",
                    ),
                ],
                className="task-panel center-panel",
            ),

            # RIGHT (fixed UI - hidden until double click selection)
            html.Div(
                [
                    html.Div(id="settings-title", className="panel-title"),
                    html.Div(
                        [
                            dbc.Checkbox(id="notify-third-party", label=t(lang, "task_create.settings.notify", "Notify Third-Party"), value=False),
                            dbc.Checkbox(id="record-vehicle", label=t(lang, "task_create.settings.record", "Record Vehicle No."), value=True),
                            dbc.Checkbox(id="unlink-material", label=t(lang, "task_create.settings.unlink", "Unlink rack material or not"), value=False),

                            dbc.Label(t(lang, "task_create.settings.gate", "GateOut/GateIn"), className="mt-3"),
                            dbc.Select(
                                id="gate-mode",
                                options=[
                                    {"label": t(lang, "task_create.settings.common", "Common"), "value": "common"},
                                    {"label": t(lang, "task_create.settings.gatein", "GateIn"), "value": "in"},
                                ],
                                value="common",
                            ),

                            dbc.Checkbox(id="lock-sign", label=t(lang, "task_create.settings.lock", "Lock sign"), value=True, className="mt-3"),
                            dbc.Checkbox(id="unlock-pod", label=t(lang, "task_create.settings.unlock", "unLock Pod"), value=False),

                            html.Hr(className="my-3"),

                            dbc.Button(t(lang, "task_create.settings.save_task", "Save"), id="btn-save-task", color="primary", className="w-100", n_clicks=0),
                            html.Div(id="save-msg", className="mt-2"),
                        ],
                        id="settings-body",
                        className="settings-body",
                    ),
                ],
                id="right-panel-inner",
                className="task-panel right-panel",
                style={"display": "none"},  # default: trống/ẩn
            ),
        ],
        className="task-create-wrapper",
    )


@callback(
    Output("right-panel-inner", "style"),
    Output("settings-title", "children"),
    Output("notify-third-party", "value"),
    Output("record-vehicle", "value"),
    Output("unlink-material", "value"),
    Output("gate-mode", "value"),
    Output("lock-sign", "value"),
    Output("unlock-pod", "value"),
    Input("wf-selection", "data"),
    State("wf-config", "data"),
)
def on_select_node(sel, cfg_store):
    if not sel or not isinstance(sel, dict) or not sel.get("nodeId"):
        # chưa double click task nào => panel phải trống/ẩn
        return {"display": "none"}, "", False, True, False, "common", True, False

    node_id = sel["nodeId"]
    title = sel.get("title", "")
    order = sel.get("order", None)
    header = f"[{order}] {title}" if order else title

    cfg_store = cfg_store or {}
    cfg = cfg_store.get(node_id, {})

    return (
        {"display": "block"},
        header,
        bool(cfg.get("notify_third_party", False)),
        bool(cfg.get("record_vehicle", True)),
        bool(cfg.get("unlink_material", False)),
        cfg.get("gate_mode", "common"),
        bool(cfg.get("lock_sign", True)),
        bool(cfg.get("unlock_pod", False)),
    )


# ===== Callback 2: persist changes -> wf-config (theo node đang chọn) =====
@callback(
    Output("wf-config", "data"),
    Input("notify-third-party", "value"),
    Input("record-vehicle", "value"),
    Input("unlink-material", "value"),
    Input("gate-mode", "value"),
    Input("lock-sign", "value"),
    Input("unlock-pod", "value"),
    State("wf-selection", "data"),
    State("wf-config", "data"),
    prevent_initial_call=True,
)
def persist_config(v1, v2, v3, v4, v5, v6, sel, store):
    if not sel or not isinstance(sel, dict) or not sel.get("nodeId"):
        return no_update

    store = dict(store or {})  # IMPORTANT: copy để Dash nhận thay đổi
    store[sel["nodeId"]] = {
        "notify_third_party": bool(v1),
        "record_vehicle": bool(v2),
        "unlink_material": bool(v3),
        "gate_mode": v4,
        "lock_sign": bool(v5),
        "unlock_pod": bool(v6),
    }
    return store


# ===== Callback 3: Save (panel phải) chỉ cho task đang chọn =====
@callback(
    Output("save-msg", "children"),
    Input("btn-save-task", "n_clicks"),
    State("wf-selection", "data"),
    State("wf-config", "data"),
    State("wf-state", "data"),
    prevent_initial_call=True,
)
def save_task(n, sel, cfg_store, wf_state):
    if not sel or not sel.get("nodeId"):
        return dbc.Alert("Chưa chọn task nào (double click vào task trong workflow).", color="warning", className="mb-0")

    node_id = sel["nodeId"]
    cfg_store = cfg_store or {}

    payload = {
        "nodeId": node_id,
        "order": sel.get("order"),
        "title": sel.get("title"),
        "config": cfg_store.get(node_id, {}),
        "workflow": wf_state or {},
    }

    print("[SAVE_TASK_ONLY]", json.dumps(payload, ensure_ascii=False))
    return dbc.Alert("Đã tạo payload task này (xem log server).", color="success", className="mb-0")


# ===== Modal open/close (FIX lỗi return) =====
@callback(
    Output("modal-save-workflow", "is_open"),
    Output("wf-name", "value"),
    #Output("wf-save-error", "children"),
    Input("btn-save-workflow-open", "n_clicks"),
    Input("btn-save-workflow-cancel", "n_clicks"),
    Input("btn-save-workflow-confirm", "n_clicks"),
    State("modal-save-workflow", "is_open"),
    prevent_initial_call=True,
)
def toggle_save_modal(open_n, cancel_n, confirm_n, is_open):
    trig = callback_context.triggered_id

    if trig == "btn-save-workflow-open":
        return True, "", ""  # mở modal + clear

    if trig == "btn-save-workflow-cancel":
        return False, no_update, ""  # đóng modal + clear message

    # confirm: không đóng ở đây, để callback save_workflow_all quyết định (và hiện message)
    if trig == "btn-save-workflow-confirm":
        return True, no_update, no_update

    return is_open, no_update, no_update


# ===== Save workflow tổng (Output = wf-save-error) =====
@callback(
    Output("wf-save-error", "children"),
    Input("btn-save-workflow-confirm", "n_clicks"),
    State("wf-name", "value"),
    State("wf-state", "data"),
    State("wf-config", "data"),
    prevent_initial_call=True,
)
def save_workflow_all(n, wf_name, wf_state, wf_config):
    name = (wf_name or "").strip()
    if not name:
        return dbc.Alert("Please enter a workflow name.", color="warning", className="mb-0")

    wf_state = wf_state or {}
    nodes = wf_state.get("nodes") or []
    edges = wf_state.get("edges") or []
    wf_config = wf_config or {}

    task_nodes = [x for x in nodes if isinstance(x, dict) and x.get("type") == "taskGroup"]
    task_nodes_sorted = sorted(task_nodes, key=lambda x: (x.get("position", {}).get("y", 0)))

    tasks_payload = []
    for idx, node in enumerate(task_nodes_sorted, start=1):
        node_id = node.get("id")
        data = node.get("data") or {}

        tasks_payload.append({
            "order": idx,
            "nodeId": node_id,
            "title": data.get("title"),
            "action_type": data.get("action_type"),
            "config": data.get("config", {}),
            "settings": wf_config.get(node_id, {}),
        })

    payload = {
        "workflow_name": name,
        "task_count": len(tasks_payload),
        "tasks": tasks_payload,
        "edges": edges,
    }

    print("[SAVE_WORKFLOW_ALL]", json.dumps(payload, ensure_ascii=False))

    return dbc.Alert("Workflow payload generated (see server log).", color="success", className="mb-0")