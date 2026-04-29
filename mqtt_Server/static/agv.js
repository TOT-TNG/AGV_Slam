<<<<<<< HEAD
const API_URL = "http://192.168.88.253:8000";
=======
const API_URL = "http://192.168.0.17:8000";
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574
let agvElement;
const nodes = {};

const nodePositions = {
  "StartPoint": { x: 200, y: 300 },
  "Dock01":     { x: 800, y: 300 },
  "NodeA":      { x: 400, y: 150 },
  "NodeB":      { x: 600, y: 450 },
  "NodeC":      { x: 700, y: 200 },
  "1":          { x: 500, y: 555 },
  "2":          { x: 750, y: 290 } 
};

// CHỐNG LỖI NULL - chỉ gọi khi DOM sẵn sàng
document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  const mapId = params.get("map_id");

  if (mapId) {
    loadMap(mapId);
  }

  initDashboard();
});


function log(msg) {
  const logEl = document.getElementById("log");
  if (!logEl) {
    console.log("LOG:", msg);
    return;
  }
  const time = new Date().toLocaleTimeString();
  logEl.value += `[${time}] ${msg}\n`;
  logEl.scrollTop = logEl.scrollHeight;
}

function initDashboard() {
  log("Dashboard khởi động...");
  initMap();
  loadAGVs();
  loadNodes();
  startPolling(); // dùng polling thay WebSocket
  setupButtons();
  log("Dashboard sẵn sàng! Chọn AGV và điểm đến để di chuyển.");
}

function initMap() {
  const map = document.getElementById("map");
  if (!map) {
    log("LỖI: Không tìm thấy #map");
    return;
  }

  // Vẽ node
  Object.keys(nodePositions).forEach(id => {
    const pos = nodePositions[id];
    const node = document.createElement("div");
    node.className = "node";
    node.textContent = id;
    node.style.left = pos.x + "px";
    node.style.top = pos.y + "px";
    node.onclick = () => {
      const destSelect = document.getElementById("destSelect");
      if (destSelect) {
        destSelect.value = id;
        log(`Chọn điểm đến: ${id}`);
      }
    };
    map.appendChild(node);
    nodes[id] = node;
  });

  // Vẽ đường
  const edges = [
    ["StartPoint", "NodeA"], ["NodeA", "NodeB"], ["NodeB", "Dock01"],
    ["StartPoint", "Dock01"], ["NodeA", "NodeC"], ["NodeC", "Dock01"]
  ];
  edges.forEach(([a, b]) => {
    if (nodePositions[a] && nodePositions[b]) {
      const edge = document.createElement("div");
      edge.className = "edge";
      const dx = nodePositions[b].x - nodePositions[a].x;
      const dy = nodePositions[b].y - nodePositions[a].y;
      const length = Math.sqrt(dx*dx + dy*dy);
      const angle = Math.atan2(dy, dx) * 180 / Math.PI;
      edge.style.width = length + "px";
      edge.style.left = nodePositions[a].x + "px";
      edge.style.top = nodePositions[a].y + "px";
      edge.style.transform = `rotate(${angle}deg)`;
      map.appendChild(edge);
    }
  });

  // AGV
  agvElement = document.createElement("div");
  agvElement.className = "agv";
  map.appendChild(agvElement);
  log("Bản đồ đã vẽ xong!");
}

function setupButtons() {
  const sendBtn = document.getElementById("sendMove");
  if (sendBtn) {
    sendBtn.onclick = sendMove;
    sendBtn.disabled = false;
  }
}

// Polling trạng thái AGV mỗi 1s
function startPolling() {
  setInterval(async () => {
    try {
      const res = await fetch(`${API_URL}/debug/agvs`);
      if (!res.ok) return;
      const data = await res.json();
      const selected = document.getElementById("agvSelect")?.value;
      if (selected && data.agvs[selected]) {
        const state = data.agvs[selected];
        updateAGVPosition(state);
        updateStatus(state);
      }
    } catch (e) {
      // log("Polling error: " + e.message);
    }
  }, 1000);
  log("Bắt đầu polling trạng thái AGV (1s/lần)");
}

function updateAGVPosition(state) {
  if (!agvElement) return;
  
  const nodeId = state.lastNodeId || "StartPoint";
  const coord = nodePositions[nodeId] || { x: 200, y: 300 };
  
  // DÒNG QUAN TRỌNG: bật animation mượt
  agvElement.style.transition = "left 1.8s ease, top 1.8s ease";
  
  // Di chuyển mượt đến tọa độ mới
  agvElement.style.left = coord.x + "px";
  agvElement.style.top = coord.y + "px";
  
  // Log nhẹ để thấy đang di chuyển
  console.log(`AGV đang di chuyển đến: ${nodeId} (${coord.x}, ${coord.y})`);
}

function updateStatus(state) {
  const statusEl = document.getElementById("status");
  if (!statusEl) return;
  
  const isRunning = !state.paused && state.orderId;
  setRunningEffect(isRunning);
  
  statusEl.innerHTML = `
    <b>AGV:</b> ${state.serialNumber || "Unknown"}<br>
    <b>Vị trí:</b> ${state.lastNodeId || "StartPoint"}<br>
    <b>Pin:</b> ${state.batteryState?.batteryCharge ?? 0}%<br>
    <b>Order:</b> ${state.orderId?.slice(0,8) || "None"}<br>
    <b>Trạng thái:</b> <span class="${isRunning ? 'text-green-400 animate-pulse' : 'text-red-500'}">
      ${isRunning ? "ĐANG CHẠY" : "DỪNG"}
    </span>
  `;
}

async function loadAGVs() {
  try {
    const res = await fetch(`${API_URL}/debug/agvs`);
    const data = await res.json();
    const select = document.getElementById("agvSelect");
    if (!select) return;

    // Xóa option cũ
    select.innerHTML = '<option value="">Chọn AGV...</option>';

    Object.keys(data.agvs).forEach(id => {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = id;
      select.appendChild(opt);
    });

    if (select.options.length > 1) {
      select.value = select.options[1].value;
      document.getElementById("sendMove").disabled = false;
      log(`Đã load ${select.options.length-1} AGV`);
    }
  } catch (e) {
    log("Lỗi load AGV: " + e.message);
  }
}

function loadNodes() {
  const select = document.getElementById("destSelect");
  if (!select) return;
  select.innerHTML = '<option value="">Chọn điểm đến...</option>';
  Object.keys(nodePositions).forEach(id => {
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = id;
    select.appendChild(opt);
  });
}

async function sendMove() {
  const agvSelect = document.getElementById("agvSelect");
  const destSelect = document.getElementById("destSelect");
  if (!agvSelect || !destSelect) return;

  const agvId = agvSelect.value;
  const dest = destSelect.value;
  if (!agvId || !dest) {
    log("Vui lòng chọn AGV và điểm đến!");
    return;
  }

  log(`Đang gửi lệnh: ${agvId} → ${dest}...`);
  try {
    const res = await fetch(`${API_URL}/move`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agv_id: agvId, destination: dest })
    });

    if (res.ok) {
      const result = await res.json();
      log(`THÀNH CÔNG! Order: ${result.orderId?.slice(0,8)} → ${dest}`);
    } else {
      const error = await res.text();
      log(`LỖI ${res.status}: ${error}`);
    }
  } catch (e) {
    log(`LỖI mạng: ${e.message}`);
  }
}

async function sendAction(action) {
  const agvSelect = document.getElementById("agvSelect");
  if (!agvSelect) return;
  const agvId = agvSelect.value;
  if (!agvId) {
    log("Chưa chọn AGV!");
    return;
  }

  await fetch(`${API_URL}/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agv_id: agvId, action_type: action })
  });
  log(`ĐÃ GỬI ${action}`);
}

async function loadMap(mapId) {
  try {
<<<<<<< HEAD
    const base = "http://192.168.1.7:8000";
=======
    const base = "http://192.168.0.17:8000";
>>>>>>> 83554841fd7d3c2ff850fed616c1ce8043939574

    const [mapJson, nodeList, edgeList] = await Promise.all([
      fetch(`${base}/api/maps/${mapId}`).then(r => r.json()),
      fetch(`${base}/api/maps/${mapId}/nodes`).then(r => r.json()),
      fetch(`${base}/api/maps/${mapId}/edges`).then(r => r.json()),
    ]);

    console.log("Map loaded:", mapJson);

    window.mapResolution = mapJson.resolution || 0.05;

    drawNodes(nodeList);
    drawEdges(edgeList, nodeList);
  }
  catch (e) {
    console.error("Load map failed:", e);
  }
}
function worldToPixel(x, y) {
  const scale = 150; // scale ảnh tùy vào resolution thực tế
  return { px: x * scale, py: y * scale };
}
function drawNodes(nodesFromDB) {
  const map = document.getElementById("map");
  map.innerHTML = ""; // xoá map cũ

  nodesFromDB.forEach(n => {
    const { px, py } = worldToPixel(n.x, n.y);

    const node = document.createElement("div");
    node.className = "node";
    node.textContent = n.id;
    node.style.left = px + "px";
    node.style.top = py + "px";

    map.appendChild(node);
  });
}
function drawEdges(edgeList, nodeList) {
  const map = document.getElementById("map");

  const pos = {};
  nodeList.forEach(n => {
    const p = worldToPixel(n.x, n.y);
    pos[n.id] = p;
  });

  edgeList.forEach(e => {
    const a = pos[e.from];
    const b = pos[e.to];
    if (!a || !b) return;

    const dx = b.px - a.px;
    const dy = b.py - a.py;
    const len = Math.sqrt(dx*dx + dy*dy);
    const angle = Math.atan2(dy, dx) * 180 / Math.PI;

    const line = document.createElement("div");
    line.className = "edge";
    line.style.width = len + "px";
    line.style.left = a.px + "px";
    line.style.top = a.py + "px";
    line.style.transform = `rotate(${angle}deg)`;

    map.appendChild(line);
  });
}

