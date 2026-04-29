(function () {
  if (window.__WF_REACTFLOW_BOOTED_V13) {
    console.log("[wf] already booted v13 - skip");
    return;
  }
  window.__WF_REACTFLOW_BOOTED_V13 = true;

  const REACTFLOW_UMD = "https://unpkg.com/@xyflow/react@12.5.6/dist/umd/index.js";
  console.log("[wf] LOADED version=2026-01-07-13");

  function loadScriptOnce(src, key) {
    if (window[key]) return Promise.resolve();
    window[key] = true;
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.async = true;
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  function setDash(id, props) {
    if (window.dash_clientside && typeof window.dash_clientside.set_props === "function") {
      window.dash_clientside.set_props(id, props);
      return true;
    }
    const el = document.getElementById(id);
    if (el && typeof el._dashprivate_setProps === "function") {
      el._dashprivate_setProps(props);
      return true;
    }
    return false;
  }

  function ensureJsxRuntimeShim() {
    if (!window.React) return;
    const rt = {
      jsx: window.React.createElement,
      jsxs: window.React.createElement,
      Fragment: window.React.Fragment,
    };
    window.jsxRuntime = window.jsxRuntime || rt;
    window.ReactJSXRuntime = window.ReactJSXRuntime || rt;
    window.reactJsxRuntime = window.reactJsxRuntime || rt;
    console.log("[wf] jsx-runtime shim ready");
  }

  function uniqueId(prefix) {
    return prefix + "_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 7);
  }

  // ---- bind drag tiles (left list) ----
  function bindTiles() {
    document.querySelectorAll(".task-tile").forEach((t) => {
      if (t.dataset.wfBound === "1") return;
      t.dataset.wfBound = "1";
      t.setAttribute("draggable", "true");

      t.addEventListener("dragstart", (ev) => {
        const payloadStr = t.dataset.payload || "";
        const label = t.dataset.command || t.textContent?.trim() || "";
        if (!payloadStr) return;

        console.log("[wf] dragstart", label, payloadStr);

        ev.dataTransfer.effectAllowed = "copy";
        // Firefox needs text/plain to allow drop
        ev.dataTransfer.setData("text/plain", label || "task");
        ev.dataTransfer.setData("application/wf-template", payloadStr);
      });
    });
  }

  function boot(root) {
    if (root.dataset.wfMounted === "1") return;
    root.dataset.wfMounted = "1";
    console.log("[wf] mounting on #wf-root");

    if (!window.React || !window.ReactDOM) return console.error("[wf] React/ReactDOM not found");
    if (!window.ReactFlow) return console.error("[wf] ReactFlow UMD not found");

    const React = window.React;
    const ReactDOM = window.ReactDOM;
    const RF = window.ReactFlow;

    const {
      ReactFlow,
      Background,
      Handle,
      Position,
    } = RF;

    // ===== Layout constants (sequential vertical) =====
    const BASE_X = 140;
    const BASE_Y = 60;
    const SLOT_H = 200;         // khoảng cách giữa các task (đều nhau)
    const COLOR = "#2563eb";

    // ===== Custom Edge: full arrow from handle-bottom to handle-top =====
    function WfArrowEdge(props) {
      const { id, sourceX, sourceY, targetX, targetY, style } = props;

      const stroke = (style && style.stroke) || COLOR;
      const strokeWidth = (style && style.strokeWidth) || 3;

      const x = (sourceX + targetX) / 2;

      // cố định arrow size
      const arrowLen = 16;
      const arrowWid = 12;

      // tính từ mép handle (đúng ý Sếp)
      const startY = sourceY + 2;
      const tipY = targetY - 2;

      const baseY = tipY - arrowLen;

      const linePath = `M ${x} ${startY} L ${x} ${baseY}`;

      const leftX = x - arrowWid / 2;
      const rightX = x + arrowWid / 2;
      const arrowPath = `M ${leftX} ${baseY} L ${x} ${tipY} L ${rightX} ${baseY} Z`;

      return React.createElement(
        React.Fragment,
        null,
        React.createElement("path", {
          key: id + ":line",
          className: "react-flow__edge-path wf-edge-path",
          d: linePath,
          fill: "none",
          stroke,
          strokeWidth,
          strokeLinecap: "round",
          strokeLinejoin: "round",
        }),
        React.createElement("path", {
          key: id + ":arrow",
          className: "wf-edge-arrow",
          d: arrowPath,
          fill: stroke,
          stroke: "none",
        })
      );
    }

    // ✅ SỬA: không còn “đệm” 4 step nữa. Có bao nhiêu step thì render bấy nhiêu.
    function TaskGroupNode({ id, data }) {
      const order = data.order || 0;

      const onDoubleClick = (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const payload = {
          nodeId: id,
          title: data.title || "",
          steps: (data.steps || []).map((s) => (s.kind || s)),
          order,
        };
        setDash("wf-selection", { data: payload });
      };

      const onDelete = (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        if (typeof window.__WF_REMOVE_NODE === "function") {
          window.__WF_REMOVE_NODE(id);
        }
      };

      const steps = Array.isArray(data.steps) ? data.steps : [];
      const rows = steps.map((s, idx) => {
        const label = s ? (s.kind || s) : "";
        return { idx, label };
      });

      return React.createElement(
        "div",
        { className: "wf-nodewrap", onDoubleClick },

        // số thứ tự nằm bên trái, “trên canvas”
        React.createElement("div", { className: "wf-order" }, order),

        // nút xoá
        React.createElement("button", { className: "wf-del", onClick: onDelete, title: ((window.__WF_I18N && window.__WF_I18N.remove) || "Remove") }, "×"),

        // Handles (ẩn) để edge bám đúng vị trí
        React.createElement(Handle, {
          type: "target",
          position: Position.Top,
          id: "t",
          style: { opacity: 0, width: 10, height: 10, top: -6 },
        }),
        React.createElement(Handle, {
          type: "source",
          position: Position.Bottom,
          id: "b",
          style: { opacity: 0, width: 10, height: 10, bottom: -6 },
        }),

        // card
        React.createElement(
          "div",
          { className: "wf-node" },
          React.createElement(
            "div",
            { className: "wf-node__left" },
            React.createElement("div", { className: "wf-node__title" }, data.title || ((window.__WF_I18N && window.__WF_I18N.task_group) || "Task Group"))
          ),
          React.createElement(
            "div",
            { className: "wf-node__right" },
            rows.map((r) =>
              React.createElement(
                "div",
                {
                  key: id + ":row:" + r.idx,
                  className: "wf-step",
                  style: { opacity: r.label ? 1 : 0.55 },
                },
                React.createElement("div", { className: "wf-step__idx" }, r.idx + 1),
                React.createElement("div", { className: "wf-step__pill" }, r.label)
              )
            )
          )
        )
      );
    }

    const nodeTypes = { taskGroup: TaskGroupNode };
    const edgeTypes = { wfArrow: WfArrowEdge };

    function buildEdgesFromOrder(taskNodes) {
      const edges = [];
      for (let i = 0; i < taskNodes.length - 1; i++) {
        const a = taskNodes[i].id;
        const b = taskNodes[i + 1].id;
        edges.push({
          id: "e_" + a + "__" + b,
          source: a,
          target: b,
          type: "wfArrow",
          style: { stroke: COLOR, strokeWidth: 3 },
        });
      }
      return edges;
    }

    function App() {
      const [nodes, setNodes] = React.useState(() => []);
      const [edges, setEdges] = React.useState(() => []);

      // expose remover
      React.useEffect(() => {
        window.__WF_REMOVE_NODE = (nodeId) => {
          setNodes((prev) => prev.filter((n) => n.id !== nodeId));
          // nếu xoá node đang chọn => clear selection panel
          setDash("wf-selection", { data: null });
        };
      }, []);

      // relayout + order numbering
      const relayout = React.useCallback((prevNodes) => {
        const tasks = prevNodes.slice(); // only tasks exist
        const next = tasks.map((n, idx) => {
          const pos = { x: BASE_X, y: BASE_Y + idx * SLOT_H };
          const order = idx + 1;
          return {
            ...n,
            position: pos,
            data: { ...(n.data || {}), order },
          };
        });
        return next;
      }, []);

      // whenever nodes change -> relayout + rebuild edges + update scroll height
      React.useEffect(() => {
        setNodes((prev) => relayout(prev));
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, [nodes.length]); // only when count changes

      React.useEffect(() => {
        const taskNodes = nodes;
        const nextEdges = buildEdgesFromOrder(taskNodes);
        setEdges(nextEdges);

        // đẩy state ra Dash (debug / lưu sau này)
        setDash("wf-state", { data: { nodes: taskNodes, edges: nextEdges, selection: null } });

        // set chiều cao root để scroll hoạt động (outer .wf-scroll sẽ overflow:auto)
        const totalH = BASE_Y + Math.max(1, taskNodes.length) * SLOT_H + 260;
        root.style.height = totalH + "px";
      }, [nodes]);

      window.__WF_ADD_NODE_FROM_PAYLOAD = (payload) => {
        const title = payload.title || "Task Group";
        const stepsRaw = Array.isArray(payload.steps) ? payload.steps : [];
        const steps = stepsRaw.map((k, i) => ({ id: "s" + (i + 1), kind: k, config: {} }));

        const newId = uniqueId("tg");

        setNodes((prev) => {
          const newNode = {
            id: newId,
            type: "taskGroup",
            position: { x: BASE_X, y: BASE_Y }, // relayout sẽ đặt đúng slot
            data: { title, steps, order: prev.length + 1 },
            sourcePosition: Position.Bottom,
            targetPosition: Position.Top,
            draggable: false,
          };
          return [...prev, newNode];
        });
      };

      return React.createElement(
        ReactFlow,
        {
          nodes,
          edges,
          nodeTypes,
          edgeTypes,

          // TẮT zoom/pan để dùng scroll
          fitView: false,
          panOnDrag: false,
          zoomOnScroll: false,
          zoomOnPinch: false,
          zoomOnDoubleClick: false,
          minZoom: 1,
          maxZoom: 1,
          defaultViewport: { x: 0, y: 0, zoom: 1 },
        },
        React.createElement(Background, { key: "bg" })
      );
    }

    // Mount
    if (ReactDOM.createRoot) ReactDOM.createRoot(root).render(React.createElement(App));
    else ReactDOM.render(React.createElement(App), root);

    // Native drop on root
    if (!root.dataset.nativeDropBound) {
      root.dataset.nativeDropBound = "1";

      root.addEventListener("dragover", (e) => {
        e.preventDefault();
        if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
      });

      root.addEventListener("drop", (e) => {
        e.preventDefault();
        const raw = e.dataTransfer.getData("application/wf-template");
        const text = e.dataTransfer.getData("text/plain");
        console.log("[wf] native drop", raw, text);
        if (!raw) return;

        let payload;
        try {
          payload = JSON.parse(raw);
        } catch {
          console.warn("[wf] drop payload JSON parse failed");
          return;
        }
        if (typeof window.__WF_ADD_NODE_FROM_PAYLOAD === "function") {
          window.__WF_ADD_NODE_FROM_PAYLOAD(payload);
        }
      });
    }

    // bind tiles
    bindTiles();
    new MutationObserver(bindTiles).observe(document.body, { childList: true, subtree: true });
  }

  function bootWithRetry() {
    const root = document.getElementById("wf-root");
    if (!root) return setTimeout(bootWithRetry, 200);
    boot(root);
  }

  document.addEventListener("DOMContentLoaded", async () => {
    ensureJsxRuntimeShim();
    await loadScriptOnce(REACTFLOW_UMD, "__WF_REACTFLOW_UMD_LOADED");
    bootWithRetry();
  });
})();
