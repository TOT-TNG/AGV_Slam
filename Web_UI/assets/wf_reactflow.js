(function () {
  if (window.__WF_REACTFLOW_BOOTED_V15) {
    console.log("[wf] already booted v15 - skip");
    return;
  }
  window.__WF_REACTFLOW_BOOTED_V15 = true;

  const REACTFLOW_UMD = "https://unpkg.com/@xyflow/react@12.5.6/dist/umd/index.js";
  console.log("[wf] LOADED version=2026-03-23-v15");

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
  }

  function uniqueId(prefix) {
    return prefix + "_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8);
  }

  function deepClone(obj) {
    try {
      return JSON.parse(JSON.stringify(obj));
    } catch {
      return obj;
    }
  }

  function bindTiles() {
    document.querySelectorAll(".task-tile").forEach((t) => {
      if (t.dataset.wfBound === "1") return;
      t.dataset.wfBound = "1";
      t.setAttribute("draggable", "true");

      t.addEventListener("dragstart", (ev) => {
        const payloadStr = t.dataset.payload || "";
        const label = t.dataset.command || t.textContent?.trim() || "";
        if (!payloadStr) return;

        ev.dataTransfer.effectAllowed = "copy";
        ev.dataTransfer.setData("text/plain", label || "task");
        ev.dataTransfer.setData("application/wf-template", payloadStr);
      });
    });
  }

  function boot(root) {
    if (root.dataset.wfMounted === "1") return;
    root.dataset.wfMounted = "1";

    if (!window.React || !window.ReactDOM) {
      console.error("[wf] React/ReactDOM not found");
      return;
    }
    if (!window.ReactFlow) {
      console.error("[wf] ReactFlow UMD not found");
      return;
    }

    const React = window.React;
    const ReactDOM = window.ReactDOM;
    const RF = window.ReactFlow;
    const {
      ReactFlow,
      Background,
      Handle,
      Position,
    } = RF;

    const BASE_X = 140;
    const BASE_Y = 60;
    const SLOT_H = 200;
    const COLOR = "#2563eb";

    function defaultTitleForAction(actionType) {
      if (actionType === "MOVE_TO_POSE") return "Transfer Goods";
      if (actionType === "PICKUP") return "Pickup";
      if (actionType === "DROP") return "Drop";
      return "Task";
    }

    function summarizeConfig(actionType, config) {
      const cfg = config || {};

      if (actionType === "MOVE_TO_POSE") {
        return "Pose: " + (cfg.name || "-");
      }

      if (actionType === "PICKUP") {
        return "Lift";
      }

      if (actionType === "DROP") {
        return "Putdown";
      }

      const keys = Object.keys(cfg);
      if (!keys.length) return "";
      return keys.map((k) => `${k}: ${cfg[k]}`).join(" | ");
    }

    function normalizeNodePayload(rawPayload) {
      const payload = rawPayload || {};

      if (payload.action_type) {
        const actionType = String(payload.action_type).trim().toUpperCase();
        const config = deepClone(payload.config || {});
        const title = defaultTitleForAction(actionType);

        return {
          title,
          action_type: actionType,
          config,
          steps: [
            { id: "s1", kind: title, config: {} },
            { id: "s2", kind: summarizeConfig(actionType, config), config: deepClone(config) },
          ],
        };
      }

      const title = payload.title || "Task";
      const stepsRaw = Array.isArray(payload.steps) ? payload.steps : [];
      const steps = stepsRaw.map((k, i) => ({
        id: "s" + (i + 1),
        kind: typeof k === "string" ? k : (k?.kind || "Step"),
        config: deepClone(k?.config || {}),
      }));

      return {
        title,
        action_type: payload.action_type || null,
        config: deepClone(payload.config || {}),
        steps,
      };
    }

    function buildNodeDataFromPayload(rawPayload, order) {
      const normalized = normalizeNodePayload(rawPayload);

      return {
        title: normalized.title,
        order,
        action_type: normalized.action_type,
        config: normalized.config || {},
        steps: normalized.steps || [],
      };
    }

    function nodeToRuntimeTemplate(node) {
      return {
        id: node.id,
        order: node.data?.order || 0,
        title: node.data?.title || "",
        action_type: node.data?.action_type || null,
        config: deepClone(node.data?.config || {}),
      };
    }

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

    function WfArrowEdge(props) {
      const { id, sourceX, sourceY, targetX, targetY, style } = props;

      const stroke = (style && style.stroke) || COLOR;
      const strokeWidth = (style && style.strokeWidth) || 3;

      const x = (sourceX + targetX) / 2;
      const arrowLen = 16;
      const arrowWid = 12;

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

    function TaskGroupNode({ id, data }) {
      const order = data.order || 0;
      const title = data.title || "Task";

      const onDoubleClick = (ev) => {
        ev.preventDefault();
        ev.stopPropagation();

        setDash("wf-selection", {
          data: {
            nodeId: id,
            title: data.title || "",
            action_type: data.action_type || null,
            config: deepClone(data.config || {}),
            steps: deepClone(data.steps || []),
            order: data.order || 0,
          },
        });
      };

      const onDelete = (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        if (typeof window.__WF_REMOVE_NODE === "function") {
          window.__WF_REMOVE_NODE(id);
        }
      };

      const rows = Array.isArray(data.steps) ? data.steps : [];

      return React.createElement(
        "div",
        { className: "wf-nodewrap", onDoubleClick },

        React.createElement("div", { className: "wf-order" }, order),

        React.createElement(
          "button",
          {
            className: "wf-del",
            onClick: onDelete,
            title: "Remove",
          },
          "×"
        ),

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

        React.createElement(
          "div",
          { className: "wf-node" },

          React.createElement(
            "div",
            { className: "wf-node__left" },
            React.createElement("div", { className: "wf-node__title" }, title)
          ),

          React.createElement(
            "div",
            { className: "wf-node__right", style: { padding: "10px 12px" } },
            rows.map((r, idx) =>
              React.createElement(
                "div",
                {
                  key: (r?.id || idx) + "_" + id,
                  className: "wf-step",
                  style: { opacity: r?.kind ? 1 : 0.55 },
                },
                React.createElement("div", { className: "wf-step__idx" }, idx + 1),
                React.createElement("div", { className: "wf-step__pill" }, r?.kind || "-")
              )
            )
          )
        )
      );
    }

    const nodeTypes = { taskGroup: TaskGroupNode };
    const edgeTypes = { wfArrow: WfArrowEdge };

    function App() {
      const [nodes, setNodes] = React.useState([]);
      const [edges, setEdges] = React.useState([]);

      const relayout = React.useCallback((prevNodes) => {
        return prevNodes.map((n, idx) => ({
          ...n,
          position: { x: BASE_X, y: BASE_Y + idx * SLOT_H },
          data: { ...(n.data || {}), order: idx + 1 },
        }));
      }, []);

      React.useEffect(() => {
        window.__WF_REMOVE_NODE = (nodeId) => {
          setNodes((prev) => prev.filter((n) => n.id !== nodeId));
          setDash("wf-selection", { data: null });
        };

        window.__WF_ADD_NODE_FROM_PAYLOAD = (payload) => {
          setNodes((prev) => {
            const node = {
              id: uniqueId("tg"),
              type: "taskGroup",
              position: { x: BASE_X, y: BASE_Y },
              data: buildNodeDataFromPayload(payload, prev.length + 1),
              sourcePosition: Position.Bottom,
              targetPosition: Position.Top,
              draggable: false,
            };
            return [...prev, node];
          });
        };

        window.__WF_UPDATE_NODE = (nodeId, patch) => {
          if (!nodeId) return;

          setNodes((prev) =>
            prev.map((n) => {
              if (n.id !== nodeId) return n;

              const nextActionType = patch.action_type ?? n.data?.action_type ?? null;
              const nextConfig = patch.config ? deepClone(patch.config) : deepClone(n.data?.config || {});
              const nextTitle = nextActionType
                ? defaultTitleForAction(nextActionType)
                : (patch.title ?? n.data?.title ?? "Task");

              const nextSteps = nextActionType
                ? [
                    { id: "s1", kind: nextTitle, config: {} },
                    { id: "s2", kind: summarizeConfig(nextActionType, nextConfig), config: deepClone(nextConfig) },
                  ]
                : deepClone(n.data?.steps || []);

              return {
                ...n,
                data: {
                  ...(n.data || {}),
                  title: nextTitle,
                  action_type: nextActionType,
                  config: nextConfig,
                  steps: nextSteps,
                },
              };
            })
          );
        };

        window.__WF_EXPORT_TEMPLATE = () => {
          const ordered = [...nodes].sort((a, b) => (a.data?.order || 0) - (b.data?.order || 0));
          return {
            workflow_name: "Workflow_" + new Date().toISOString(),
            tasks: ordered.map(nodeToRuntimeTemplate),
          };
        };
      }, [nodes]);

      React.useEffect(() => {
        setNodes((prev) => relayout(prev));
      }, [nodes.length, relayout]);

      React.useEffect(() => {
        const nextEdges = buildEdgesFromOrder(nodes);
        setEdges(nextEdges);

        setDash("wf-state", {
          data: {
            nodes: nodes.map((n) => ({
              id: n.id,
              type: n.type,
              position: n.position,
              data: deepClone(n.data || {}),
            })),
            edges: deepClone(nextEdges),
            tasks: [...nodes]
              .sort((a, b) => (a.data?.order || 0) - (b.data?.order || 0))
              .map(nodeToRuntimeTemplate),
          },
        });

        const totalH = BASE_Y + Math.max(1, nodes.length) * SLOT_H + 260;
        root.style.height = totalH + "px";
      }, [nodes]);

      return React.createElement(
        ReactFlow,
        {
          nodes,
          edges,
          nodeTypes,
          edgeTypes,
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

    if (ReactDOM.createRoot) {
      ReactDOM.createRoot(root).render(React.createElement(App));
    } else {
      ReactDOM.render(React.createElement(App), root);
    }

    if (!root.dataset.nativeDropBound) {
      root.dataset.nativeDropBound = "1";

      root.addEventListener("dragover", (e) => {
        e.preventDefault();
        if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
      });

      root.addEventListener("drop", (e) => {
        e.preventDefault();
        const raw = e.dataTransfer.getData("application/wf-template");
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

    bindTiles();
    new MutationObserver(bindTiles).observe(document.body, {
      childList: true,
      subtree: true,
    });
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