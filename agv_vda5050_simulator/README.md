# Multi-AGV VDA5050 Simulator (Python)

A structured, update-friendly 2D simulator for testing a Fleet Manager / Server that communicates with AGVs using MQTT topics per AGV in the VDA5050 topic format.

## Highlights

- Multi-AGV simulator, each AGV is an independent object
- Multi-layer/floor map support; nodes and edges can carry a `layer` field
- Elevator simulator agent with HTTP command API and MQTT state topic
- MQTT topics per AGV: `uagv/v3/<manufacturer>/<serialNumber>/<topic>`
- Simplified but practical VDA5050 message handling:
  - `order`
  - `instantActions`
  - `state`
  - `connection`
  - `visualization`
  - `factsheet`
- 2D simulation with map graph on top of a background image
- Pygame UI for live monitoring, menu actions, graph editing, and operator control
- Runtime menu bar:
  - `Map`: load map, create new map, save map, add/move/delete points and paths
  - `AGV`: create a new simulated AGV
- Click an AGV to open a control panel
- Supports multiple AGV simulation types such as `SLAM`, `QR`, and `LINE` while keeping the same VDA5050 topic contract
- Fault injection: warning / error / fatal / obstacle / power off / MQTT disconnect
- Battery drain and state publishing loop
- Clean modular file structure for easy updates

## Folder structure

```text
agv_vda5050_simulator/
├── main.py
├── requirements.txt
├── README.md
├── config/
│   ├── simulator.json
│   └── sample_graph.json
├── assets/
│   └── generated_map.png
├── sim/
│   ├── __init__.py
│   ├── app.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── agv_agent.py
│   │   ├── faults.py
│   │   ├── models.py
│   │   ├── power.py
│   │   ├── simulator.py
│   │   └── state_machine.py
│   ├── map/
│   │   ├── __init__.py
│   │   ├── graph.py
│   │   └── loader.py
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── pygame_app.py
│   │   └── widgets.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── geometry.py
│   │   └── helpers.py
│   └── vda5050/
│       ├── __init__.py
│       ├── messages.py
│       └── mqtt_client.py
└── tools/
    └── send_sample_orders.py
```

## Install

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

### 1) Start an MQTT broker
Example with Mosquitto:

```bash
mosquitto -v
```

### 2) Run simulator

```bash
python main.py
```

For large fleets, tune MQTT publish rate in `config/simulator.json` under `simulation`:

```json
"state_publish_hz": 1,
"connection_publish_hz": 0.2,
"visualization_publish_hz": 1
```

These values are per AGV. With 200 AGVs, `state_publish_hz: 1` means about 200 state messages per second.

### 3) Send sample orders

```bash
python tools/send_sample_orders.py
```

## MQTT topic format

Each AGV has its own namespace:

```text
uagv/v3/tot/AGV01/order
uagv/v3/tot/AGV01/instantActions
uagv/v3/tot/AGV01/state
uagv/v3/tot/AGV01/connection
uagv/v3/tot/AGV01/visualization
uagv/v3/tot/AGV01/factsheet
```

Elevators publish a simple retained state on:

```text
/elevator1/state
```

Example payload:

```json
{
  "elevator_id": 1,
  "current_floor": 0,
  "target_floor": 1,
  "door": "closed",
  "status": "moving",
  "occupied_by": "AGV01"
}
```

## Elevator API

The simulator starts an HTTP API from `config/simulator.json` under `api`:

```json
"api": {"enabled": true, "host": "127.0.0.1", "port": 8088}
```

Supported commands:

```text
POST /elevators/{id}/call       {"job_id": "...", "floor": 0}
POST /elevators/{id}/open-door  {"job_id": "..."}
POST /elevators/{id}/close-door {"job_id": "..."}
POST /elevators/{id}/go         {"job_id": "...", "target_floor": 1}
POST /elevators/{id}/release    {"job_id": "..."}
```

`open-door` and `close-door` will capture an AGV positioned on the elevator node. You can also pass optional `agv_id` to pick a specific AGV. When `go` reaches the target floor, the occupied AGV is moved to the configured floor node and its `layer` changes.

Elevator map config example:

```json
{
  "elevator_id": 1,
  "node_id": "N8",
  "floors": [0, 1],
  "floor_nodes": {"0": "N8", "1": "N16"},
  "current_floor": 0
}
```

## UI controls

- Top-left menu bar:
  - `Map > Load map`: load a graph JSON map
  - `Map > New map`: create a blank editable map with custom name, width, and height in meters
  - `Map > Add SLAM map`: select a SLAM PNG image as the map background, then `Save map` to store it in the map JSON
  - `Map > Add floor layer / Previous layer / Next layer`: create and switch floor layers
  - `Map > Save map`: save current graph JSON
  - `Map > Upload map`: post the current map to the server API configured in `config/simulator.json` under `map_upload.url`
  - `Map > Add point / Add path / Move point / Delete item`: switch graph editor modes
  - `AGV > New AGV`: add a simulated AGV on the selected point or first map point, with type, length, width, and stop distance
  - `Setting > Server`: edit the map upload server URL and payload parameters, then save them to `config/simulator.json`
  - `Setting > MQTT broker`: edit broker host, port, keepalive, enabled flag, and VDA topic namespace; saving reconnects the simulated AGVs
- The right-side tool panel is contextual: choose `Map` to show map-editing tools, or `AGV` to show AGV creation/control tools.
- Scroll the right-side tool panel with the mouse wheel when the selected AGV exposes more controls than fit on screen.
- Map navigation: mouse wheel zooms in/out around the cursor, middle mouse drag pans the map, `0` resets the map view.
- Left click AGV: open control panel
- When an AGV is selected, the `AGV` tool panel can switch automatic/manual mode, adjust battery, set simulated states, and control MQTT/power.
- `Toggle Obstacle` simulates an obstacle in front of the selected AGV; if it is within `stop_distance`, the AGV stops and publishes a `WARNING` in `state.errors`.
- Each AGV also checks a circular safety radius equal to its `stop_distance`; if another AGV enters that radius, it stops and publishes `PEER_AGV_IN_STOP_DISTANCE`.
- In `MANUAL` mode, use arrow keys to move: `Up/Down` forward/backward, `Left/Right` rotate, `Shift+Left/Right` strafe.
- Panel buttons:
  - Pause / Resume
  - Warning / Error / Fatal
  - Obstacle toggle
  - MQTT disconnect / reconnect
  - Power OFF / ON
  - Clear errors
- ESC closes panel


## Graph editor controls

- `N`: add node mode, then left-click on the map
- `E`: add edge mode, then click node A and node B
- `M`: move node mode, then drag a node
- `D`: delete mode, then click node or edge
- `S`: save graph to `config/sample_graph.json`
- `T`: cycle selected node type
- `B`: toggle selected edge bidirectional flag
- `Delete`: delete selected node or edge
- Right-click node: quick cycle node type
- Right-click edge: quick toggle edge direction

## Notes on VDA5050 compatibility

This project is built to be practical for server testing. It uses the `uagv/v3/...` topic namespace and keeps the message shapes close to VDA5050 workflows while remaining lightweight and readable.

Each simulated AGV subscribes and publishes under its own VDA5050 namespace, for example `uagv/v3/tot/AGV01/order` and `uagv/v3/tot/AGV01/state`. The UI is only a visual simulator and output generator for the server; behavior differences between SLAM, QR, and magnetic-line AGVs can be extended behind the same VDA5050 interface.

Supported instant actions include `startPause`, `stopPause`, `cancelOrder`, `factsheetRequest`, `stateRequest`, `visualizationRequest`, `clearErrors`, `startHibernation`, `stopHibernation`, `shutdown`, `updateCertificate`, and `trigger`.

You can extend the message models in `sim/vda5050/messages.py` if your server expects stricter fields.

## Suggested next upgrades

- Persist runtime-created AGVs back to scenario/config files
- Edge occupancy and traffic control between AGVs
- More precise action execution per node / edge
- Collision checking between AGVs
- Save / load runtime scenarios
- ROS2 bridge
