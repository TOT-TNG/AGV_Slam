window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: {
        init_map: function () {
            console.log("Smart Factory Map Editor - HOÃ€N CHá»ˆNH");

            // ELEMENTS
            const area = document.getElementById("map-design-area");
            const container = document.getElementById("map-container");
            const canvas = document.getElementById("map-canvas");
            const edgeLayer = document.getElementById("edge-layer");
            const nodeBtn = document.getElementById("add-node");
            const toolbox = document.getElementById("toolbox-panel");
            const toggleBtn = document.getElementById("toggle-toolbox-btn");
            container.style.transformOrigin = "0 0";

            // STATE
            let nodes = [], edges = [], selectedNodes = [];
            let scale = 1, panX = 0, panY = 0;
            let isPanning = false, addingNode = false;

            // SVG EDGE
            const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
            svg.style.cssText = "position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:visiblePainted;z-index:3;";
            edgeLayer.appendChild(svg);
            updateEdges();

            // ZOOM Tá»ª GIá»®A MÃ€N HÃŒNH
            area.addEventListener("wheel", e => {
                e.preventDefault();
                const rect = area.getBoundingClientRect();
                const mouseX = e.clientX - rect.left;
                const mouseY = e.clientY - rect.top;

                const delta = e.deltaY > 0 ? 0.9 : 1.1;
                const newScale = Math.max(0.1, Math.min(scale * delta, 5));

                panX = mouseX - (mouseX - panX) * (newScale / scale);
                panY = mouseY - (mouseY - panY) * (newScale / scale);
                scale = newScale;

                updateTransform();
            });

            // PAN - KÃ‰O THáº¢
            area.addEventListener("mousedown", e => {
                if (e.target !== area && !e.target.closest(".node")) return;
                isPanning = true;
                area.style.cursor = "grabbing";
                const startX = e.clientX - panX;
                const startY = e.clientY - panY;

                const move = e => {
                    panX = e.clientX - startX;
                    panY = e.clientY - startY;
                    updateTransform();
                };

                const up = () => {
                    document.removeEventListener("mousemove", move);
                    document.removeEventListener("mouseup", up);
                    isPanning = false;
                    area.style.cursor = "grab";
                };

                document.addEventListener("mousemove", move);
                document.addEventListener("mouseup", up);
            });

            // TRANSFORM CHUNG
            function updateTransform() {
                container.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
                document.getElementById("zoom-level").textContent = `Zoom: ${Math.round(scale * 100)}%`;
            }

            // THÃŠM NODE
            nodeBtn.onclick = () => {
                addingNode = !addingNode;
                nodeBtn.classList.toggle("active");
            };

            area.onclick = e => {
                /*if (e.target.closest("#edge-layer")) return;*/
                if (!addingNode || e.target.closest(".node")) return;
                e.stopPropagation();

                const rect = area.getBoundingClientRect();
                const clickX = e.clientX - rect.left;
                const clickY = e.clientY - rect.top;

                // CHUYá»‚N Tá»ŒA Äá»˜ CHUá»˜T â†’ Tá»ŒA Äá»˜ TRONG CANVAS
                const x = (clickX - panX) / scale;
                const y = (clickY - panY) / scale;

                const node = document.createElement("div");
                node.className = "node";
                node.style.left = (x - 15) + "px";
                node.style.top = (y - 15) + "px";
                node.dataset.x = Math.round(x);
                node.dataset.y = Math.round(y);
                node.dataset.name = "Node";
                node.dataset.id = "n" + Date.now();

                canvas.appendChild(node);
                nodes.push(node);
                addingNode = false;
                nodeBtn.classList.remove("active");
                makeInteractive(node);
            };

            // NODE INTERACTIVE
            function makeInteractive(node) {
                // CHá»ŒN NHIá»€U
                node.onclick = e => {
                    e.stopPropagation();
                    if (e.ctrlKey) {
                        const i = selectedNodes.indexOf(node);
                        if (i === -1) {
                            selectedNodes.push(node);
                            node.classList.add("selected");
                        } else {
                            selectedNodes.splice(i, 1);
                            node.classList.remove("selected");
                        }
                    } else {
                        selectedNodes.forEach(n => n.classList.remove("selected"));
                        selectedNodes = [node];
                        node.classList.add("selected");
                    }
                };

                // KÃ‰O NODE â€” BÃM SÃT CHUá»˜T, KHÃ”NG NHáº¢Y, KHÃ”NG CHáº¶N DBLCLICK
                let isDragging = false;
                node.onmousedown = e => {
                    if (e.button !== 0) return;
                    isDragging = true;
                    e.stopPropagation();

                    const startX = e.clientX;
                    const startY = e.clientY;
                    const startLeft = parseFloat(node.style.left) + 15;
                    const startTop = parseFloat(node.style.top) + 15;

                    const move = e => {
                        if (!isDragging) return;
                        const dx = (e.clientX - startX) / scale;
                        const dy = (e.clientY - startY) / scale;
                        const newX = startLeft + dx;
                        const newY = startTop + dy;

                        node.style.left = (newX - 15) + "px";
                        node.style.top = (newY - 15) + "px";
                        node.dataset.x = Math.round(newX);
                        node.dataset.y = Math.round(newY);
                        updateEdges();
                    };

                    const up = () => {
                        isDragging = false;
                        document.removeEventListener("mousemove", move);
                        document.removeEventListener("mouseup", up);
                    };

                    document.addEventListener("mousemove", move);
                    document.addEventListener("mouseup", up);
                };

                // DOUBLE-CLICK â†’ Má»ž PROPERTIES
                node.ondblclick = e => {
                    e.stopPropagation();
                    showProperties(node);
                };
            }

            // EDGE
            function connectNodes(a, b) {
                edges.push({ from: a, to: b });
                updateEdges();
            }

            function updateEdges() {
                // XÃ³a vÃ  khá»Ÿi táº¡o láº¡i SVG
                svg.innerHTML = "";
                svg.setAttribute("width", "100%");
                svg.setAttribute("height", "100%");
                svg.setAttribute("viewBox", "0 0 3000 2000");
                svg.style.pointerEvents = "auto"; // Cho phÃ©p click xuyÃªn xuá»‘ng node

                edges.forEach(edge => {
                    const a = edge.from, b = edge.to;
                    const x1 = parseFloat(a.style.left) + 15;
                    const y1 = parseFloat(a.style.top) + 15;
                    const x2 = parseFloat(b.style.left) + 15;
                    const y2 = parseFloat(b.style.top) + 15;

                    const angle = Math.atan2(y2 - y1, x2 - x1) * 180 / Math.PI;
                    const len = Math.hypot(x2 - x1, y2 - y1);
                    const midX = (x1 + x2) / 2;
                    const midY = (y1 + y2) / 2;

                    // táº¡o group
                    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
                    g.style.pointerEvents = "auto"; // Cho phÃ©p click/dblclick vÃ o Ä‘Æ°á»ng ná»‘i
                    g.dataset.from = a.dataset.id;
                    g.dataset.to = b.dataset.id;
                    g.dataset.direction = edge.direction || "both";
                    g.dataset.speed = edge.speed || "0.5";
                    g.dataset.lidar = edge.lidar || "on";
                    g.dataset.blocked = edge.blocked || "[]";

                    // tÃ¡ch mÅ©i tÃªn xa nhau
                    const arrowOffset = Math.min(Math.max(len * 0.18, 12), 40);

                    // mÃ u sáº¯c theo tráº¡ng thÃ¡i
                    const fillColor =
                        g.dataset.direction === "blocked" ? "#dc3545" :
                        g.dataset.direction === "forward" ? "#198754" :
                        g.dataset.direction === "backward" ? "#ff9500" : "#4b9cff";

                    // ná»™i dung SVG
                    g.innerHTML = `
                        <g transform="translate(${midX},${midY}) rotate(${angle})">
                            <rect x="${-len/2}" y="-7.5" width="${len}" height="15" rx="7.5"
                                fill="${fillColor}" pointer-events="visiblePainted"/>
                            <path d="M ${-arrowOffset},-5 L ${-arrowOffset+8},0 L ${-arrowOffset},5 Z"
                                fill="white" pointer-events="visiblePainted"/>
                            <path d="M ${arrowOffset},-5 L ${arrowOffset-8},0 L ${arrowOffset},5 Z"
                                fill="white" pointer-events="visiblePainted"/>
                        </g>
                    `;
                    svg.appendChild(g);
                    if (!window.edgeClickBound) {
                        window.edgeClickBound = true;
                        edgeLayer.addEventListener("dblclick", e => {
                            const g = e.target.closest("g");
                            if (!g || !g.dataset.from) return;
                            console.log("âœ… Double click captured via delegation:", g.dataset);

                            const fromNode = document.querySelector(`[data-id="${g.dataset.from}"]`);
                            const toNode = document.querySelector(`[data-id="${g.dataset.to}"]`);
                            if (!fromNode || !toNode) return;

                            // má»Ÿ panel edge
                            const edgeTargetEl = document.getElementById("edge-target");
                            if (edgeTargetEl) {
                                edgeTargetEl.textContent = `Edge: ${fromNode.dataset.name} â†’ ${toNode.dataset.name}`;
                            }
                            const panel = document.getElementById("edge-properties-panel");
                            if (panel) {
                                panel.classList.add("show");
                                panel.style.right = "0";
                            }
                        });
                    }
                });
                // --- FIX DOUBLE CLICK EDGE ---
                // Báº¯t toÃ n bá»™ sá»± kiá»‡n double click trong edge-layer
                document.getElementById("edge-layer")?.addEventListener("dblclick", function (e) {
                    const group = e.target.closest("g[data-from]");
                    if (!group) return; // KhÃ´ng click trÃºng edge tháº­t

                    e.stopPropagation();
                    console.log("Double click edge!", group.dataset);

                    const fromNode = document.querySelector(`[data-id="${group.dataset.from}"]`);
                    const toNode = document.querySelector(`[data-id="${group.dataset.to}"]`);
                    if (!fromNode || !toNode) return;

                    // Hiá»‡n properties panel
                    window.currentEdge = group;
                    document.getElementById("edge-target").textContent =
                        `Edge: ${fromNode.dataset.name} â†’ ${toNode.dataset.name}`;

                    const dir = group.dataset.direction || "both";
                    const speed = group.dataset.speed || "0.5";
                    const lidar = group.dataset.lidar !== "off";
                    const blocked = JSON.parse(group.dataset.blocked || "[]");

                    const wait = (id, cb) => {
                        const check = () => {
                            const el = document.getElementById(id);
                            if (el) cb(el);
                            else setTimeout(check, 50);
                        };
                        check();
                    };

                    wait("edge-direction", el => el.value = dir);
                    wait("edge-speed", el => el.value = speed);
                    wait("edge-lidar", el => el.checked = lidar);
                    wait("edge-blocked-agvs", el => el.value = blocked);
                    wait("blocked-agvs-container", el => {
                        el.style.display = dir === "blocked" ? "block" : "none";
                    });

                    const panel = document.getElementById("edge-properties-panel");
                    if (panel) {
                        panel.classList.add("show");
                        panel.style.right = "0";
                    }
                });

                // Gáº®N Sá»° KIá»†N DOUBLE-CLICK CHO EDGE
                /*svg.querySelectorAll("g").forEach(g => {
                    g.addEventListener("dblclick", function (e) {
                        e.stopPropagation();

                        // láº¥y group gáº§n nháº¥t (vÃ¬ cÃ³ thá»ƒ click trÃºng <rect> hoáº·c <path>)
                        const targetGroup = e.target.closest("g");
                        if (!targetGroup || !targetGroup.dataset.from) return;
                        console.log("Double click edge:", targetGroup?.dataset);
                        console.log("Double click edge:", targetGroup.dataset);

                        const fromNode = document.querySelector(`[data-id="${targetGroup.dataset.from}"]`);
                        const toNode = document.querySelector(`[data-id="${targetGroup.dataset.to}"]`);
                        if (!fromNode || !toNode) return;

                        // LÆ°u edge hiá»‡n táº¡i
                        window.currentEdge = targetGroup;

                        // Cáº­p nháº­t tiÃªu Ä‘á» panel
                        const edgeTargetEl = document.getElementById("edge-target");
                        if (edgeTargetEl) {
                            edgeTargetEl.textContent = `Edge: ${fromNode.dataset.name} â†’ ${toNode.dataset.name}`;
                        }

                        // Láº¥y dá»¯ liá»‡u
                        const dir = targetGroup.dataset.direction || "both";
                        const speed = targetGroup.dataset.speed || "0.5";
                        const lidar = targetGroup.dataset.lidar !== "off";
                        const blocked = JSON.parse(targetGroup.dataset.blocked || "[]");

                        // Äá»£i cho input xuáº¥t hiá»‡n rá»“i má»›i gÃ¡n
                        const wait = (id, cb) => {
                            const chk = () => {
                                const el = document.getElementById(id);
                                if (el) cb(el);
                                else setTimeout(chk, 50);
                            };
                            chk();
                        };

                        wait("edge-direction", el => el.value = dir);
                        wait("edge-speed", el => el.value = speed);
                        wait("edge-lidar", el => el.checked = lidar);
                        wait("edge-blocked-agvs", el => el.value = blocked);
                        wait("blocked-agvs-container", el => {
                            el.style.display = dir === "blocked" ? "block" : "none";
                        });

                        const panel = document.getElementById("edge-properties-panel");
                        if (panel) {
                            panel.classList.add("show");
                            panel.style.right = "0";
                        }
                    });
                });*/
            }

            // CONTEXT MENU
            area.oncontextmenu = e => {
                const node = e.target.closest(".node");
                if (!node) return;
                e.preventDefault();
                if (window.ctx) window.ctx.remove();

                window.ctx = document.createElement("div");
                window.ctx.className = "context-menu";
                window.ctx.style.left = e.pageX + "px";
                window.ctx.style.top = e.pageY + "px";
                window.ctx.innerHTML = `
                    <div class="context-item" id="connect">Connect</div>
                    <div class="context-item" id="delete">Delete</div>
                `;
                document.body.appendChild(window.ctx);

                window.ctx.onclick = ev => {
                    if (ev.target.id === "connect" && selectedNodes.length === 2) {
                        connectNodes(selectedNodes[0], selectedNodes[1]);
                        updateEdges();
                        selectedNodes.forEach(n => n.classList.remove("selected"));
                        selectedNodes = [];
                    }
                    if (ev.target.id === "delete") {
                        edges = edges.filter(e => e.from !== node && e.to !== node);
                        node.remove();
                        nodes = nodes.filter(n => n !== node);
                        updateEdges();
                    }
                    window.ctx.remove();
                };
            };

            // PROPERTIES
            window.showProperties = function(node) {
                // Äá»ŒC Dá»® LIá»†U Tá»ª NODE â†’ KHÃ”NG DÃ™NG BIáº¾N TOÃ€N Cá»¤C
                const n = node;

                // Cáº¬P NHáº¬T Tá»ªNG Ã” Má»˜T â†’ Báº®T BUá»˜C DÃ™NG setTimeout Äá»‚ DASH â€œNGHEâ€ ÄÆ¯á»¢C
                setTimeout(() => {
                    document.getElementById("prop-target").textContent = `Node: ${n.dataset.name || "Node"}`;
                    document.getElementById("prop-name").value = n.dataset.name || "Node";
                    document.getElementById("prop-x").value = n.dataset.x || 0;
                    document.getElementById("prop-y").value = n.dataset.y || 0;
                    document.getElementById("prop-speed").value = n.dataset.speed || 0.5;
                    document.getElementById("prop-lidar").checked = n.dataset.lidar !== "off";

                    // DROPDOWN: DÃ™NG DISPATCH Äá»‚ Ã‰P DASH Cáº¬P NHáº¬T
                    const rotateEvt = new Event('input', { bubbles: true });
                    const funcEvt = new Event('input', { bubbles: true });
                    const rotateEl = document.getElementById("prop-rotate");
                    const funcEl = document.getElementById("prop-function");

                    rotateEl.value = n.dataset.rotate || "0";
                    funcEl.value = n.dataset.function || "normal";

                    rotateEl.dispatchEvent(rotateEvt);
                    funcEl.dispatchEvent(funcEvt);
                }, 10);

                window.currentNode = node;
                const panel = document.getElementById("properties-panel");
                panel.classList.add("show");
                panel.style.right = "0";
            };

            // LÆ¯U + HIá»†N THÃ”NG BÃO Äáº¸P - CHá»ˆ LÆ¯U NODE ÄANG CHá»ŒN
                        document.getElementById("prop-save").onclick = function() {
                if (!window.currentNode) return;
                const n = window.currentNode;

                n.dataset.name = document.getElementById("prop-name").value.trim() || "Node";
                n.dataset.x = document.getElementById("prop-x").value;
                n.dataset.y = document.getElementById("prop-y").value;
                n.dataset.rotate = document.getElementById("prop-rotate").value;
                n.dataset.function = document.getElementById("prop-function").value;
                n.dataset.speed = document.getElementById("prop-speed").value;
                n.dataset.lidar = document.getElementById("prop-lidar").checked ? "on" : "off";

                n.style.left = (n.dataset.x - 15) + "px";
                n.style.top = (n.dataset.y - 15) + "px";
                n.style.transform = `rotate(${n.dataset.rotate}deg)`;

                updateEdges();
                closeProperties();

                // THÃ”NG BÃO XANH LÃ
                const t = document.createElement("div");
                t.innerHTML = `<div style="position:fixed;bottom:20px;right:20px;background:#34C759;color:#fff;padding:15px 25px;border-radius:16px;font-weight:600;z-index:9999;box-shadow:0 8px 20px rgba(0,0,0,0.25);">
                    ÄÃƒ LÆ¯U: ${n.dataset.name}<br>
                    <small>Chá»©c nÄƒng: ${n.dataset.function} | GÃ³c: ${n.dataset.rotate}Â°</small>
                </div>`;
                document.body.appendChild(t);
                setTimeout(() => t.remove(), 2800);
            };

            document.getElementById("prop-close").onclick = closeProperties;
            function closeProperties() {
                const panel = document.getElementById("properties-panel");
                panel.classList.remove("show");
                panel.style.right = "-280px";
            }

            document.querySelectorAll('#prop-lidar input[type="radio"]').forEach(radio => {
                radio.addEventListener('change', function() {
                    if (this.checked) {
                        const other = this.value === "on" 
                            ? document.querySelector('#prop-lidar input[value="off"]')
                            : document.querySelector('#prop-lidar input[value="on"]');
                        if (other) other.checked = false;
                    }
                });
            });

            document.getElementById("prop-lidar")?.addEventListener("change", function() {
                const onText = document.getElementById("lidar-on-text");
                const offText = document.getElementById("lidar-off-text");
                if (this.checked) {
                    onText.style.display = "none";
                    offText.style.display = "inline";
                    offText.style.color = "#0d6efd";
                } else {
                    onText.style.display = "inline";
                    offText.style.display = "none";
                }
            });

            const initEdgeProperties = () => {
                const wait = (id, callback) => {
                    const check = () => {
                        const el = document.getElementById(id);
                        if (el) callback(el);
                        else setTimeout(check, 50);
                    };
                    check();
                };

                document.getElementById("edge-layer")?.addEventListener("dblclick", e => {
                    const g = e.target.closest("g");
                    if (!g || !g.dataset.from) return;
                    e.stopPropagation();

                    const fromNode = document.querySelector(`[data-id="${g.dataset.from}"]`);
                    const toNode = document.querySelector(`[data-id="${g.dataset.to}"]`);
                    if (!fromNode || !toNode) return;

                    window.currentEdge = g;

                    const targetEl = document.getElementById("edge-target");
                    if (targetEl)
                        targetEl.textContent = `Edge: ${fromNode.dataset.name} â†’ ${toNode.dataset.name}`;


                    const dir = g.dataset.direction || "both";
                    const speed = g.dataset.speed || "0.5";
                    const lidar = g.dataset.lidar !== "off";
                    const blocked = JSON.parse(g.dataset.blocked || "[]");

                    wait("edge-direction", el => el.value = dir);
                    wait("edge-speed", el => el.value = speed);
                    wait("edge-lidar", el => el.checked = lidar);
                    wait("edge-blocked-agvs", el => el.value = blocked);
                    wait("blocked-agvs-container", el => el.style.display = dir === "blocked" ? "block" : "none");

                    const panel = document.getElementById("edge-properties-panel");
                    if (panel) {
                        panel.classList.add("show");
                        panel.style.right = "0";
                    }
                });

                wait("edge-save", btn => btn.addEventListener("click", () => {
                    if (!window.currentEdge) return;
                    const g = window.currentEdge;

                    const dir = document.getElementById("edge-direction")?.value || "both";
                    const speed = document.getElementById("edge-speed")?.value || "0.5";
                    const lidar = document.getElementById("edge-lidar")?.checked ? "on" : "off";
                    const blocked = JSON.stringify(document.getElementById("edge-blocked-agvs")?.value || []);

                    g.dataset.direction = dir;
                    g.dataset.speed = speed;
                    g.dataset.lidar = lidar;
                    g.dataset.blocked = blocked;

                    const rect = g.querySelector("rect");
                    if (rect) {
                        rect.setAttribute("fill", 
                            dir === "blocked" ? "#dc3545" :
                            dir === "forward" ? "#198754" :
                            dir === "backward" ? "#ff9500" : "#4b9cff"
                        );
                    }

                    const t = document.createElement("div");
                    t.innerHTML = `<div style="position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#34C759;color:white;padding:14px 30px;border-radius:16px;font-weight:600;z-index:9999;">
                        ÄÃƒ LÆ¯U EDGE: ${dir === "blocked" ? "Cáº¤M" : dir.toUpperCase()} | ${speed}m/s
                    </div>`;
                    document.body.appendChild(t);
                    setTimeout(() => t.remove(), 2500);

                    document.getElementById("edge-properties-panel").style.right = "-280px";
                }));

                wait("edge-close", () => document.getElementById("edge-properties-panel").style.right = "-280px");
                wait("edge-direction", el => el.addEventListener("change", () => {
                    document.getElementById("blocked-agvs-container").style.display = 
                        el.value === "blocked" ? "block" : "none";
                }));
            };

            if (document.readyState === "complete") initEdgeProperties();
            else window.addEventListener("load", initEdgeProperties);

            // TOGGLE TOOLBOX
            toggleBtn.onclick = () => {
                toolbox.classList.toggle("open");
                toggleBtn.textContent = toolbox.classList.contains("open") ? "â†’" : "â†";
            };
        }
    }
});

(function () {
    function initAssistant() {
        if (window.__assistantInit) return;
        window.__assistantInit = true;

        const toast = document.getElementById("assistant-toast");
        const titleEl = document.getElementById("assistant-title");
        const msgEl = document.getElementById("assistant-message");
        const closeBtn = document.getElementById("assistant-close");

        if (!toast || !titleEl || !msgEl || !closeBtn) return;

        let hideTimer = null;
        const idleTitle = "Tro ly ao";
        const idleMessage = "";

        function toIdle() {
            toast.classList.remove("level-info", "level-warning", "level-error");
            toast.classList.add("idle");
            titleEl.textContent = idleTitle;
            msgEl.textContent = idleMessage;
        }

        function showAlert(payload) {
            const level = (payload.level || "info").toLowerCase();
            const title = payload.title || "Tro ly ao";
            const message = payload.message || "";

            titleEl.textContent = title;
            msgEl.textContent = message;

            toast.classList.remove("idle", "level-info", "level-warning", "level-error", "alerting");
            toast.classList.add("level-" + level);
            toast.classList.add("alerting");

            if (hideTimer) clearTimeout(hideTimer);
            hideTimer = setTimeout(toIdle, 10000);
            setTimeout(() => toast.classList.remove("alerting"), 900);
        }

        closeBtn.addEventListener("click", function () {
            if (hideTimer) clearTimeout(hideTimer);
            toIdle();
        });

        function connectWs() {
            const proto = window.location.protocol === "https:" ? "wss://" : "ws://";
            const host = window.location.hostname || "localhost";
            const wsUrl = proto + host + ":8000/ws";

            let ws;
            try {
                ws = new WebSocket(wsUrl);
            } catch (err) {
                console.warn("[assistant] WS init failed:", err);
                setTimeout(connectWs, 3000);
                return;
            }

            ws.onopen = function () {
                console.log("[assistant] WS connected:", wsUrl);
            };
            ws.onmessage = function (evt) {
                try {
                    const data = JSON.parse(evt.data);
                    if (data && data.type === "assistant_alert") {
                        showAlert(data);
                    }
                } catch (e) {
                    console.warn("[assistant] WS message parse failed:", e);
                }
            };
            ws.onclose = function () {
                console.warn("[assistant] WS closed, retrying...");
                setTimeout(connectWs, 3000);
            };
            ws.onerror = function () {
                ws.close();
            };
        }

        toIdle();
        connectWs();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAssistant);
    } else {
        initAssistant();
    }
})();
