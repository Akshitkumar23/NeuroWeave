// ─── STATE ──────────────────────────────────────────────────────
let activeSessionId = null;
let eventSource     = null;
let currentReportMd = "";
let logCount        = 0;
let logsOpen        = false;
let speechRecognitionInstance = null;
let isSpeechRecording = false;

// ─── INIT ────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    // Run button
    document.getElementById("execute-btn").addEventListener("click", initiateOrchestration);

    // File drop zone
    const dropZone  = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");
    dropZone.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", (e) => handleFileUpload(e.target.files[0]));
    dropZone.addEventListener("dragover",  (e) => { e.preventDefault(); dropZone.style.borderColor = "#6366f1"; });
    dropZone.addEventListener("dragleave", ()  => { dropZone.style.borderColor = ""; });
    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.style.borderColor = "";
        if (e.dataTransfer.files.length > 0) handleFileUpload(e.dataTransfer.files[0]);
    });

    // Load session history
    loadSessionHistory();

    // Restore saved key
    const savedKey      = localStorage.getItem("neuroweave_api_key");
    const savedProvider = localStorage.getItem("neuroweave_provider") || "gemini";
    if (savedKey) {
        document.getElementById("api-key-input").value    = savedKey;
        document.getElementById("provider-select").value  = savedProvider;
    }

    checkKeyStatus();
});

// ─── LOGS SIDEBAR TOGGLE ─────────────────────────────────────────
function toggleLogs() {
    const sidebar  = document.getElementById("logs-sidebar");
    const overlay  = document.getElementById("logs-overlay");
    const notif    = document.getElementById("logs-notif");
    logsOpen = !logsOpen;
    sidebar.classList.toggle("open", logsOpen);
    overlay.classList.toggle("active", logsOpen);
    if (logsOpen && notif) notif.style.display = "none";
}

// ─── SECTION COLLAPSE ────────────────────────────────────────────
function toggleSection(bodyId) {
    const body  = document.getElementById(bodyId);
    const arrow = body.previousElementSibling
                      ? body.previousElementSibling.querySelector(".cp-toggle i")
                      : null;
    body.classList.toggle("hidden");
    if (arrow) arrow.style.transform = body.classList.contains("hidden") ? "rotate(0deg)" : "rotate(180deg)";
}

// ─── TAB SWITCHING ───────────────────────────────────────────────
function switchTab(tabId) {
    document.querySelectorAll(".tab-pane").forEach(p => p.classList.add("hidden"));
    document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
    document.getElementById(tabId).classList.remove("hidden");
    // Activate matching tab button
    const tabMap = { "graph-tab": "tab-btn-graph", "report-tab": "tab-btn-report", "timeline-tab": "tab-btn-timeline" };
    const btn = document.getElementById(tabMap[tabId]);
    if (btn) btn.classList.add("active");
}

// ─── KEY STATUS CHECK ────────────────────────────────────────────
async function checkKeyStatus() {
    try {
        const res  = await fetch("/api/key-status");
        const data = await res.json();
        const badge = document.getElementById("api-mode-badge");
        if (!badge) return;
        if (data.active_providers && data.active_providers.includes("ollama")) {
            badge.className = "api-badge api-sim";
            badge.innerHTML = `<i class="fa-solid fa-microchip"></i> Local Model (Ollama)`;
            badge.style.color = "#8b5cf6";
            badge.style.border = "1px solid rgba(139, 92, 246, 0.3)";
        } else if (data.active_count > 0) {
            badge.className = "api-badge api-live";
            badge.innerHTML = `<i class="fa-solid fa-circle-check"></i> Live — ${data.active_providers.join(", ")}`;
        } else {
            badge.className = "api-badge api-sim";
            badge.innerHTML = `<i class="fa-solid fa-circle-info"></i> Simulation Mode`;
        }
    } catch(e) { console.log("Key status check error:", e); }
}

function handleProviderChange() {
    const provider = document.getElementById("provider-select").value;
    const keyInput = document.getElementById("api-key-input");
    const saveBtn = document.querySelector(".btn-save");
    
    if (provider === "ollama") {
        keyInput.style.display = "none";
        saveBtn.style.display = "none";
    } else {
        keyInput.style.display = "block";
        saveBtn.style.display = "inline-block";
    }
}

// ─── SAVE API KEY ────────────────────────────────────────────────
async function saveApiKey() {
    const apiKey   = document.getElementById("api-key-input").value.trim();
    const provider = document.getElementById("provider-select").value;
    if (!apiKey && provider !== "ollama") { alert("Enter an API key first."); return; }

    localStorage.setItem("neuroweave_api_key", apiKey);
    localStorage.setItem("neuroweave_provider", provider);

    try {
        const res  = await fetch("/api/save-key", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: apiKey, provider })
        });
        const data = await res.json();
        if (data.success) {
            const btn = document.getElementById("execute-btn");
            // Brief visual feedback inline
            const saveBtn = document.querySelector(".btn-save");
            if (saveBtn) {
                saveBtn.innerHTML = `<i class="fa-solid fa-check"></i> Saved!`;
                saveBtn.style.color = "#10b981";
                setTimeout(() => {
                    saveBtn.innerHTML = `<i class="fa-solid fa-floppy-disk"></i> Save Key`;
                    saveBtn.style.color = "";
                }, 2000);
            }
            checkKeyStatus();
        }
    } catch(e) { console.log("Save key error:", e); }
}

// ─── TEMPLATES REMOVED FOR CLEAN UI ──────────────────────────────

// ─── SET STATUS ──────────────────────────────────────────────────
function setStatus(type, text) {
    const pill = document.getElementById("status-pill");
    const span = document.getElementById("status-text");
    pill.className = `status-pill status-${type}`;
    span.textContent = text;
}

// ─── INITIATE ORCHESTRATION ──────────────────────────────────────
async function initiateOrchestration() {
    const query    = document.getElementById("query-input").value.trim();
    const apiKey   = document.getElementById("api-key-input").value.trim();
    const provider = document.getElementById("provider-select").value;

    if (!query) {
        alert("Please enter a research query.");
        return;
    }
    
    if (provider !== "ollama" && !apiKey && !localStorage.getItem("neuroweave_api_key")) {
        console.log("No API key provided, fallback simulated run will execute");
    }

    if (!query) { alert("Enter a research objective first."); return; }

    // Reset log count & show logs automatically
    logCount = 0;
    document.getElementById("log-count-badge").textContent = "0";
    document.getElementById("terminal-thought-stream").innerHTML = "";

    // Clear output panels
    document.getElementById("svg-graph").innerHTML = `
        <text x="50%" y="50%" text-anchor="middle" fill="rgba(255,255,255,0.2)"
            font-size="14" font-family="Inter">Initializing execution graph...</text>`;
    document.getElementById("report-output-box").innerHTML = `
        <div class="report-empty">
            <i class="fa-solid fa-spinner fa-spin" style="font-size:32px;color:#6366f1;opacity:0.7"></i>
            <h3>Synthesizing report...</h3>
            <p>Multi-agent pipeline is running. Open <strong>Agent Logs</strong> to watch live.</p>
        </div>`;

    const btn = document.getElementById("execute-btn");
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>Initializing...</span>`;
    setStatus("running", "RUNNING — Multi-Agent Pipeline Active");

    // Show logs notif
    const notif = document.getElementById("logs-notif");
    if (notif) notif.style.display = "block";

    // Auto-save key
    if (apiKey) {
        localStorage.setItem("neuroweave_api_key", apiKey);
        localStorage.setItem("neuroweave_provider", provider);
        fetch("/api/save-key", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: apiKey, provider })
        }).then(() => checkKeyStatus()).catch(() => {});
    }

    try {
        const res  = await fetch("/api/analyze", {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify({ query, api_key: apiKey || null, provider })
        });
        const data = await res.json();
        if (data.success) {
            activeSessionId = data.session_id;
            appendLog("system", "SYSTEM", `Pipeline started — Session: ${activeSessionId}`);
            connectSSE(activeSessionId);
        } else {
            alert(`Error: ${data.message}`);
            resetRunBtn();
            setStatus("error", "ERROR — Pipeline failed to start");
        }
    } catch(e) {
        alert(`Backend unreachable: ${e}`);
        resetRunBtn();
        setStatus("error", "ERROR — Server connection failed");
    }
}

function resetRunBtn() {
    const btn = document.getElementById("execute-btn");
    btn.disabled = false;
    btn.innerHTML = `<i class="fa-solid fa-bolt"></i> <span>Run Analysis</span>`;
}

// ─── SSE CONNECTION ──────────────────────────────────────────────
function connectSSE(sessionId) {
    if (eventSource) eventSource.close();
    eventSource = new EventSource(`/api/stream/${sessionId}`);
    eventSource.onmessage = (e) => {
        const state = JSON.parse(e.data);
        updateUI(state);
    };
    eventSource.onerror = () => {
        eventSource.close();
        resetRunBtn();
        loadSessionHistory();
    };
}

// ─── MAIN UI UPDATE ──────────────────────────────────────────────
function updateUI(state) {
    const status     = (state.status || "").toLowerCase();
    const activeAgent = (state.active_agent || "").toLowerCase();

    // Status pill
    const done = status === "completed" || status === "degraded";
    const fail = status === "failed";
    if (done)       setStatus("done",    "DONE — Report Ready");
    else if (fail)  setStatus("error",   "ERROR — Pipeline Failed");
    else            setStatus("running", `RUNNING — ${agentLabel(activeAgent)}`);

    // Run button
    if (done || fail) {
        resetRunBtn();
    } else {
        const btn = document.getElementById("execute-btn");
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>${agentLabel(activeAgent)}</span>`;
    }

    // Logs
    renderLogs(state.logs || []);

    // Graph
    plotGraph(state.tasks || {}, activeAgent);

    // Timeline
    plotTimeline(state.traces || []);

    // Confidence
    const conf = state.average_confidence || 0;
    document.getElementById("confidence-bar").style.width   = `${conf * 100}%`;
    document.getElementById("confidence-value").textContent = conf.toFixed(2);

    // Telemetry
    const m = state.metrics || {};
    document.getElementById("tel-model").textContent       = activeAgent ? activeAgent.toUpperCase() : "—";
    document.getElementById("tel-tokens-in").textContent   = m.total_input_tokens  || 0;
    document.getElementById("tel-tokens-out").textContent  = m.total_output_tokens || 0;
    document.getElementById("tel-cost").textContent        = `$${(m.total_estimated_cost_usd || 0).toFixed(6)}`;
    document.getElementById("tel-replans").textContent     = m.replanning_cycle_count || 0;
    const toolsTotal = Object.values(m.tool_calls_summary || {}).reduce((a,b) => a+b, 0);
    document.getElementById("tel-tools").textContent       = toolsTotal;

    // Report
    const report = state.working_memory ? state.working_memory.final_report : null;
    if (report) {
        currentReportMd = report;
        renderReport(report);
        switchTab("report-tab");
        const meta = document.getElementById("report-meta");
        if (meta) meta.textContent = `Confidence: ${conf.toFixed(2)} · Session: ${activeSessionId ? activeSessionId.slice(0,8) : "—"}`;
    }
}

function agentLabel(agent) {
    const map = {
        intent_analyzer: "Analyzing Intent...",
        planner:         "Planning Task DAG...",
        researcher:      "Researching Web Sources...",
        analyzer:        "Running Calculations...",
        critic:          "Auditing Quality...",
        debate_engine:   "Running Debate...",
        synthesizer:     "Generating Report..."
    };
    return map[agent] || "Processing...";
}

// ─── RENDER LOGS ─────────────────────────────────────────────────
function renderLogs(logs) {
    const stream = document.getElementById("terminal-thought-stream");
    const prevCount = logCount;
    
    // Only append new entries
    if (logs.length > logCount) {
        for (let i = logCount; i < logs.length; i++) {
            const log = logs[i];
            appendLog(log.type, log.agent, log.message, log.timestamp);
        }
        logCount = logs.length;
        document.getElementById("log-count-badge").textContent = logCount;

        // Show notification if sidebar is closed
        if (!logsOpen && logCount > prevCount) {
            const notif = document.getElementById("logs-notif");
            if (notif) notif.style.display = "block";
        }
    }
}

function appendLog(type, agent, message, timestamp) {
    const stream = document.getElementById("terminal-thought-stream");
    const row = document.createElement("div");
    row.className = `log-entry log-${type || "info"}`;

    const timeStr = timestamp
        ? new Date(timestamp * 1000).toTimeString().slice(0, 8)
        : new Date().toTimeString().slice(0, 8);

    const badgeClass = getBadgeClass(agent);
    row.innerHTML = `
        <span class="log-badge ${badgeClass}">${(agent || "SYS").toUpperCase()}</span>
        <span class="log-time">[${timeStr}]</span>
        <span class="log-text">${escHtml(message)}</span>`;
    stream.appendChild(row);
    stream.scrollTop = stream.scrollHeight;
}

function getBadgeClass(agent) {
    const map = {
        system:          "badge-system",
        intent_analyzer: "badge-intent",
        planner:         "badge-planner",
        researcher:      "badge-researcher",
        analyzer:        "badge-analyzer",
        critic:          "badge-critic",
        debate_engine:   "badge-debate",
        synthesizer:     "badge-synthesizer"
    };
    return map[(agent||"").toLowerCase()] || "badge-system";
}

function escHtml(s) {
    return (s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

// ─── RENDER REPORT (Markdown → HTML) ────────────────────────────
function renderReport(md) {
    const box = document.getElementById("report-output-box");
    if (!md) { box.innerHTML = ""; return; }
    window.chartQueue = [];
    box.innerHTML = parseMarkdown(md);
    if (window.chartQueue && window.chartQueue.length > 0) {
        window.chartQueue.forEach(item => {
            const ctx = document.getElementById(item.id);
            if (ctx) {
                try {
                    new Chart(ctx, JSON.parse(item.config));
                } catch(e) { console.error("Chart JSON parse error:", e); }
            }
        });
        window.chartQueue = [];
    }
}

function parseMarkdown(md) {
    const lines  = md.split(/\r?\n/);
    const blocks = [];
    let inTable  = false, tableRows = [];
    let inList   = false, listItems = [];
    let inCode   = false, codeBuf   = [], codeType = "";

    function flushTable() {
        if (!tableRows.length) return;
        let h = '<table>';
        const isDivider = (r) => r.every(c => /^[-:\s]+$/.test(c));
        if (tableRows.length > 1 && isDivider(tableRows[1])) {
            h += '<thead><tr>' + tableRows[0].map(c => `<th>${inlineMarkdown(c)}</th>`).join('') + '</tr></thead>';
            h += '<tbody>' + tableRows.slice(2).map(r =>
                '<tr>' + r.map(c => `<td>${inlineMarkdown(c)}</td>`).join('') + '</tr>').join('') + '</tbody>';
        } else {
            h += '<tbody>' + tableRows.map(r =>
                '<tr>' + r.map(c => `<td>${inlineMarkdown(c)}</td>`).join('') + '</tr>').join('') + '</tbody>';
        }
        h += '</table>';
        blocks.push(h);
        tableRows = []; inTable = false;
    }
    function flushList() {
        if (!listItems.length) return;
        blocks.push('<ul>' + listItems.map(i => `<li>${inlineMarkdown(i)}</li>`).join('') + '</ul>');
        listItems = []; inList = false;
    }
    function flushCode() {
        if (!codeBuf.length) return;
        if (codeType === "json chart") {
            const chartId = "chart-" + Math.random().toString(36).substr(2, 9);
            blocks.push(`<canvas id="${chartId}"></canvas>`);
            window.chartQueue = window.chartQueue || [];
            window.chartQueue.push({ id: chartId, config: codeBuf.join('\n') });
        } else {
            blocks.push(`<pre><code>${escHtml(codeBuf.join('\n'))}</code></pre>`);
        }
        codeBuf = []; inCode = false; codeType = "";
    }

    for (const line of lines) {
        const t = line.trim();

        // Code fence
        if (t.startsWith("```")) {
            if (inCode) { flushCode(); }
            else        { if (inTable) flushTable(); if (inList) flushList(); inCode = true; codeType = t.slice(3).trim(); }
            continue;
        }
        if (inCode) { codeBuf.push(line); continue; }

        // HR
        if (/^---+$/.test(t)) {
            if (inTable) flushTable(); if (inList) flushList();
            blocks.push('<hr>'); continue;
        }

        // Table row
        if (t.startsWith("|") && t.endsWith("|")) {
            if (inList) flushList();
            inTable = true;
            tableRows.push(t.slice(1,-1).split("|").map(c => c.trim()));
            continue;
        } else if (inTable) flushTable();

        // List item
        if (/^[-*] /.test(t)) {
            if (inTable) flushTable();
            inList = true;
            listItems.push(t.slice(2));
            continue;
        } else if (inList) flushList();

        // Blank line
        if (!t) continue;

        // Alert blocks: > [!TYPE]
        const alertMatch = t.match(/^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]/i);
        if (alertMatch) {
            const typeMap = { NOTE:"info", TIP:"tip", IMPORTANT:"info", WARNING:"warning", CAUTION:"caution" };
            const cls = typeMap[alertMatch[1].toUpperCase()] || "info";
            blocks.push(`<blockquote class="${cls}">`); continue;
        }
        if (t.startsWith(">")) {
            blocks.push(`<blockquote>${inlineMarkdown(t.slice(1).trim())}</blockquote>`); continue;
        }

        // Headings
        if      (t.startsWith("# "))   { blocks.push(`<h1>${inlineMarkdown(t.slice(2))}</h1>`); continue; }
        else if (t.startsWith("## "))  { blocks.push(`<h2>${inlineMarkdown(t.slice(3))}</h2>`); continue; }
        else if (t.startsWith("### ")) { blocks.push(`<h3>${inlineMarkdown(t.slice(4))}</h3>`); continue; }

        // Bibliography [^n]: ...
        const bib = t.match(/^\[\^(\d+)\]:\s*(.*)/);
        if (bib) {
            blocks.push(`<div class="bib-item" id="bib-${bib[1]}">
                <sup class="bib-num">[${bib[1]}]</sup> ${inlineMarkdown(bib[2])}</div>`);
            continue;
        }

        // Regular paragraph
        blocks.push(`<p>${inlineMarkdown(t)}</p>`);
    }

    if (inTable) flushTable();
    if (inList)  flushList();
    if (inCode)  flushCode();

    return blocks.join("\n");
}

function inlineMarkdown(text) {
    return text
        .replace(/\*\*(.*?)\*\*/g,       '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g,           '<em>$1</em>')
        .replace(/`([^`]+)`/g,           '<code>$1</code>')
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
        .replace(/\[\^(\d+)\](?!:)/g,    '<sup><a href="#bib-$1">[$1]</a></sup>');
}

// ─── PLOT SVG GRAPH ──────────────────────────────────────────────
function plotGraph(tasks, activeAgent) {
    const svg      = document.getElementById("svg-graph");
    svg.innerHTML  = "";

    const taskList = Object.values(tasks);
    if (taskList.length === 0) return;

    const emojiMap = { researcher:"🔍", analyzer:"📊", critic:"⚖️", planner:"🗺️", intent_analyzer:"🤖", synthesizer:"📝" };

    // Layer by dependency depth
    const layers = {};
    taskList.forEach(t => {
        const depth = (function d(id) {
            const node = tasks[id];
            if (!node || !node.dependencies?.length) return 0;
            return 1 + Math.max(...node.dependencies.map(d));
        })(t.id);
        (layers[depth] = layers[depth] || []).push(t);
    });

    const keys        = Object.keys(layers).sort((a,b) => a-b);
    const W           = svg.getBoundingClientRect().width || 760;
    const H           = parseInt(svg.getAttribute("height")) || 420;
    const marginX     = 90;
    const availW      = W - 2 * marginX;
    const stepX       = keys.length > 1 ? availW / (keys.length - 1) : 0;
    const coords      = {};

    keys.forEach((k, li) => {
        const col   = layers[k];
        const cx    = marginX + li * stepX;
        col.forEach((t, ri) => {
            const cy = (H / (col.length + 1)) * (ri + 1);
            coords[t.id] = { x: cx, y: cy };
        });
    });

    // Draw arrows
    taskList.forEach(t => {
        const tgt = coords[t.id];
        (t.dependencies || []).forEach(dep => {
            const src = coords[dep];
            if (!src || !tgt) return;
            const dx = tgt.x - src.x, dy = tgt.y - src.y;
            const dist = Math.hypot(dx, dy) || 1;
            const r    = 26;
            const ln   = document.createElementNS("http://www.w3.org/2000/svg", "line");
            ln.setAttribute("x1", src.x + r*dx/dist);
            ln.setAttribute("y1", src.y + r*dy/dist);
            ln.setAttribute("x2", tgt.x - r*dx/dist);
            ln.setAttribute("y2", tgt.y - r*dy/dist);
            ln.setAttribute("stroke", t.status === "failed" ? "#ef4444" : "#6366f1");
            ln.setAttribute("stroke-width", "1.5");
            ln.setAttribute("stroke-dasharray", t.status === "pending" ? "5,3" : "none");
            ln.setAttribute("marker-end", `url(#${t.status==="failed"?"arrow-fail":"arrow"})`);
            ln.setAttribute("opacity", "0.6");
            svg.appendChild(ln);
        });
    });

    // Draw nodes
    taskList.forEach(t => {
        const c = coords[t.id];
        if (!c) return;

        const g = document.createElementNS("http://www.w3.org/2000/svg", "g");

        // Glow for running
        if (t.status === "running") {
            const glow = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            glow.setAttribute("cx", c.x); glow.setAttribute("cy", c.y); glow.setAttribute("r", 36);
            glow.setAttribute("fill", "rgba(99,102,241,0.15)");
            glow.setAttribute("class", "node-glow");
            g.appendChild(glow);
        }

        const colorMap = { pending:"#1e2235", running:"#312e81", completed:"#064e3b", failed:"#450a0a" };
        const strokeMap = { pending:"rgba(255,255,255,0.1)", running:"#6366f1", completed:"#10b981", failed:"#ef4444" };

        const circ = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        circ.setAttribute("cx", c.x); circ.setAttribute("cy", c.y); circ.setAttribute("r", 26);
        circ.setAttribute("fill", colorMap[t.status] || "#1e2235");
        circ.setAttribute("stroke", strokeMap[t.status] || "rgba(255,255,255,0.1)");
        circ.setAttribute("stroke-width", "2");
        g.appendChild(circ);

        const em = document.createElementNS("http://www.w3.org/2000/svg", "text");
        em.setAttribute("x", c.x); em.setAttribute("y", c.y + 6);
        em.setAttribute("text-anchor", "middle"); em.setAttribute("font-size", "16");
        em.textContent = emojiMap[t.assigned_agent] || "⚙️";
        g.appendChild(em);

        // Title label above
        const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
        label.setAttribute("x", c.x); label.setAttribute("y", c.y - 34);
        label.setAttribute("text-anchor", "middle");
        label.setAttribute("font-size", "11"); label.setAttribute("font-family", "Inter");
        label.setAttribute("fill", "rgba(226,232,240,0.85)");
        const words = (t.title || "").split(" "); let line = "";
        words.slice(0, 4).forEach((w, i) => {
            const tsp = document.createElementNS("http://www.w3.org/2000/svg", "tspan");
            tsp.setAttribute("x", c.x); tsp.setAttribute("dy", i === 0 ? 0 : 13);
            tsp.textContent = w;
            label.appendChild(tsp);
        });
        g.appendChild(label);

        // Agent below
        const agentLbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
        agentLbl.setAttribute("x", c.x); agentLbl.setAttribute("y", c.y + 40);
        agentLbl.setAttribute("text-anchor", "middle");
        agentLbl.setAttribute("font-size", "9"); agentLbl.setAttribute("font-family", "JetBrains Mono, monospace");
        agentLbl.setAttribute("fill", strokeMap[t.status] || "rgba(255,255,255,0.3)");
        agentLbl.textContent = (t.assigned_agent || "").toUpperCase();
        g.appendChild(agentLbl);

        svg.appendChild(g);
    });
}

// ─── TIMELINE WATERFALL ──────────────────────────────────────────
function plotTimeline(traces) {
    const box = document.getElementById("timeline-waterfall-box");
    if (!traces.length) {
        box.innerHTML = `<div class="report-empty" style="height:200px">
            <i class="fa-solid fa-chart-gantt"></i>
            <p>Run a query to see timing breakdown</p></div>`;
        return;
    }

    box.innerHTML = "";
    const sorted   = [...traces].sort((a,b) => (a.start_time||0) - (b.start_time||0));
    const minStart = sorted[0].start_time || 0;
    const maxEnd   = Math.max(...sorted.map(s => (s.start_time||0) + (s.duration_sec||0)));
    const total    = maxEnd - minStart || 1;
    const agentColors = {
        researcher:"#10b981", analyzer:"#f59e0b", critic:"#ef4444",
        synthesizer:"#6366f1", planner:"#8b5cf6", intent_analyzer:"#3b82f6"
    };

    sorted.forEach(span => {
        const left  = (((span.start_time||0) - minStart) / total * 100).toFixed(1);
        const width = Math.max((span.duration_sec||0) / total * 100, 2).toFixed(1);
        const color = agentColors[span.agent] || "#6366f1";
        const row   = document.createElement("div");
        row.className = "gantt-row";
        row.innerHTML = `
            <div class="gantt-label" title="${span.name || span.agent}">${span.name || span.agent} <span style="color:#64748b;font-size:9px">${(span.duration_sec||0).toFixed(2)}s</span></div>
            <div class="gantt-track">
                <div class="gantt-bar" style="left:${left}%;width:${width}%;background:${color};opacity:0.85">
                    <span style="font-size:9px;color:#fff;padding-left:4px">${(span.duration_sec||0).toFixed(2)}s</span>
                </div>
            </div>`;
        box.appendChild(row);
    });
}

// ─── LOAD SESSION HISTORY ────────────────────────────────────────
async function loadSessionHistory() {
    const list = document.getElementById("session-history-list");
    try {
        const res     = await fetch("/api/sessions");
        const data    = await res.json();
        const sessions = (data.sessions || []).slice(0, 10);
        if (!sessions.length) { list.innerHTML = `<div class="history-empty">No sessions yet</div>`; return; }
        list.innerHTML = "";
        sessions.forEach(s => {
            const item = document.createElement("div");
            item.className = "history-item";
            const statusClass = s.status === "completed" ? "hist-status-completed" :
                                s.status === "failed"    ? "hist-status-failed"    : "hist-status-running";
            item.innerHTML = `
                <span class="history-item-status ${statusClass}"></span>
                <span class="history-item-query" title="${escHtml(s.query)}">${escHtml(s.query)}</span>
                <button class="btn-delete" title="Delete session">
                    <i class="fa-solid fa-trash"></i>
                </button>`;
            
            // Click item to load archived report
            item.addEventListener("click", () => loadArchivedReport(s.session_id));
            
            // Delete button click logic
            const delBtn = item.querySelector(".btn-delete");
            delBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                deleteSession(s.session_id, item);
            });
            
            list.appendChild(item);
        });
    } catch(e) { console.error("History load error:", e); }
}

// ─── LOAD ARCHIVED REPORT ────────────────────────────────────────
async function loadArchivedReport(sessionId) {
    try {
        const res = await fetch(`/api/report/${sessionId}`);
        if (!res.ok) { alert("Report not found."); return; }
        const data = await res.json();
        activeSessionId = sessionId;
        currentReportMd = data.report || data.content || "";
        renderReport(currentReportMd);
        switchTab("report-tab");
        const meta = document.getElementById("report-meta");
        if (meta) meta.textContent = `Archived · Confidence: ${(data.confidence_score||0).toFixed(2)} · ${sessionId.slice(0,8)}`;
    } catch(e) { alert(`Could not load report: ${e}`); }
}

// ─── DOWNLOAD REPORT ─────────────────────────────────────────────
function downloadReport() {
    if (!currentReportMd) { alert("No report to download."); return; }
    const blob = new Blob([currentReportMd], { type: "text/markdown" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `neuroweave_report_${(activeSessionId||"").slice(0,8)}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

// ─── FILE UPLOAD ─────────────────────────────────────────────────
async function handleFileUpload(file) {
    if (!file) return;
    const statusEl = document.getElementById("upload-status");
    statusEl.textContent = `Uploading ${file.name}...`;
    const fd = new FormData();
    fd.append("file", file);
    try {
        const res  = await fetch("/api/upload", { method: "POST", body: fd });
        const data = await res.json();
        if (data.success) {
            statusEl.textContent = `✓ Indexed: ${file.name}`;
            statusEl.style.color = "#10b981";
        } else {
            statusEl.textContent = `✗ Failed: ${data.detail}`;
            statusEl.style.color = "#ef4444";
        }
    } catch(e) {
        statusEl.textContent = `✗ Error: ${e}`;
        statusEl.style.color = "#ef4444";
    }
}

// ─── EXPORT TO PDF ───────────────────────────────────────────────
function exportToPDF() {
    if (typeof html2pdf !== 'undefined') {
        html2pdf().from(document.getElementById('report-output-box')).save('NeuroWeave_Report.pdf');
    } else {
        alert("html2pdf library is missing.");
    }
}

// ─── WEB SPEECH API ──────────────────────────────────────────────
document.addEventListener("click", (e) => {
    const micBtn = e.target.closest("#mic-btn");
    if (micBtn) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            alert("Web Speech API not supported in this browser.");
            return;
        }

        if (isSpeechRecording) {
            if (speechRecognitionInstance) {
                speechRecognitionInstance.stop();
            }
            micBtn.classList.remove("recording");
            micBtn.innerHTML = '<i class="fa-solid fa-microphone"></i>';
            isSpeechRecording = false;
        } else {
            speechRecognitionInstance = new SpeechRecognition();
            speechRecognitionInstance.continuous = false;
            speechRecognitionInstance.interimResults = false;
            
            speechRecognitionInstance.onstart = () => {
                micBtn.classList.add("recording");
                micBtn.innerHTML = '<i class="fa-solid fa-stop"></i>';
                isSpeechRecording = true;
            };
            
            speechRecognitionInstance.onresult = (event) => {
                const queryInput = document.getElementById("query-input");
                if (queryInput) {
                    queryInput.value = event.results[0][0].transcript;
                }
            };
            
            speechRecognitionInstance.onend = () => {
                micBtn.classList.remove("recording");
                micBtn.innerHTML = '<i class="fa-solid fa-microphone"></i>';
                isSpeechRecording = false;
            };
            
            speechRecognitionInstance.onerror = (err) => {
                console.error("Speech recognition error:", err);
                micBtn.classList.remove("recording");
                micBtn.innerHTML = '<i class="fa-solid fa-microphone"></i>';
                isSpeechRecording = false;
            };
            
            speechRecognitionInstance.start();
        }
    }
});

// ─── REMOVED REDUNDANT FETCH HISTORY ─────────────────────────────

async function deleteSession(id, element) {
    try {
        const res = await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
        if (res.ok) {
            element.remove();
        } else {
            console.error("Failed to delete session");
        }
    } catch(e) {
        console.error("deleteSession error:", e);
    }
}

// ─── INGEST URL ──────────────────────────────────────────────────
async function ingestUrl(url) {
    try {
        const res = await fetch('/api/ingest-url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        return await res.json();
    } catch(e) {
        console.error("ingestUrl error:", e);
    }
}
