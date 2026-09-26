// System state trackers
let activeSessionId = null;
let eventSource = null;
let currentReportMd = "";

document.addEventListener("DOMContentLoaded", () => {
    // Setup event listeners
    document.getElementById("execute-btn").addEventListener("click", initiateOrchestration);
    
    // Drag & Drop event bindings
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");
    
    dropZone.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", (e) => handleFileUpload(e.target.files[0]));
    
    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.style.borderColor = "#8b5cf6";
    });
    dropZone.addEventListener("dragleave", () => {
        dropZone.style.borderColor = "rgba(255,255,255,0.08)";
    });
    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.style.borderColor = "rgba(255,255,255,0.08)";
        if (e.dataTransfer.files.length > 0) {
            handleFileUpload(e.dataTransfer.files[0]);
        }
    });

    // Load session histories
    loadSessionHistory();
    
    // Auto-load saved API key from localStorage
    const savedKey = localStorage.getItem("neuroweave_api_key");
    const savedProvider = localStorage.getItem("neuroweave_provider") || "gemini";
    if (savedKey) {
        document.getElementById("api-key-input").value = savedKey;
        document.getElementById("provider-select").value = savedProvider;
    }
    
    // Check server-side key status
    checkKeyStatus();
});

// Check if keys are already configured on server side
async function checkKeyStatus() {
    try {
        const res = await fetch("/api/key-status");
        const data = await res.json();
        const badge = document.getElementById("api-mode-badge");
        if (badge) {
            if (data.mode === "live") {
                badge.innerHTML = `<i class="fa-solid fa-circle-check"></i> Live Mode (${data.active_providers.join(", ")})`;
                badge.style.background = "rgba(16, 185, 129, 0.2)";
                badge.style.borderColor = "#10b981";
                badge.style.color = "#10b981";
            } else {
                badge.innerHTML = `<i class="fa-solid fa-circle-info"></i> Simulation Mode`;
                badge.style.background = "rgba(245, 158, 11, 0.15)";
                badge.style.borderColor = "#f59e0b";
                badge.style.color = "#f59e0b";
            }
        }
    } catch(e) {
        console.log("Could not check key status:", e);
    }
}

// Save API key persistently
async function saveApiKey() {
    const apiKey = document.getElementById("api-key-input").value.trim();
    const provider = document.getElementById("provider-select").value;
    
    if (!apiKey) {
        alert("Please enter an API key first.");
        return;
    }
    
    const saveBtn = document.getElementById("save-key-btn");
    if (saveBtn) {
        saveBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Saving...`;
        saveBtn.disabled = true;
    }
    
    // Save to localStorage
    localStorage.setItem("neuroweave_api_key", apiKey);
    localStorage.setItem("neuroweave_provider", provider);
    
    // Save to server .env file
    try {
        const res = await fetch("/api/save-key", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: apiKey, provider: provider })
        });
        const data = await res.json();
        if (data.success) {
            if (saveBtn) {
                saveBtn.innerHTML = `<i class="fa-solid fa-check"></i> Key Saved!`;
                saveBtn.style.background = "rgba(16, 185, 129, 0.3)";
                saveBtn.style.borderColor = "#10b981";
                setTimeout(() => {
                    saveBtn.innerHTML = `<i class="fa-solid fa-floppy-disk"></i> Save Key`;
                    saveBtn.style.background = "";
                    saveBtn.style.borderColor = "";
                    saveBtn.disabled = false;
                }, 2500);
            }
            checkKeyStatus();
        }
    } catch(e) {
        if (saveBtn) {
            saveBtn.innerHTML = `<i class="fa-solid fa-floppy-disk"></i> Save Key`;
            saveBtn.disabled = false;
        }
        alert("Saved to browser, but could not persist to server: " + e);
    }
}

// UI Drawer Control
function toggleDrawer(drawerId) {
    const drawer = document.getElementById(drawerId);
    const arrow = drawer.previousElementSibling.querySelector(".arrow");
    drawer.classList.toggle("hidden");
    if (drawer.classList.contains("hidden")) {
        arrow.style.transform = "rotate(0deg)";
    } else {
        arrow.style.transform = "rotate(180deg)";
    }
}

// UI Tabs Switching
function switchTab(tabId) {
    // Hide all tab contents
    document.querySelectorAll(".tab-content").forEach(el => el.classList.add("hidden"));
    document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active-content"));
    
    // Deactivate all tab buttons
    document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
    
    // Show selected
    const activeTab = document.getElementById(tabId);
    activeTab.classList.remove("hidden");
    activeTab.classList.add("active-content");
    
    // Highlight button
    const activeBtn = Array.from(document.querySelectorAll(".tab-btn")).find(btn => btn.getAttribute("onclick").includes(tabId));
    if (activeBtn) activeBtn.classList.add("active");
}

// Initiates the Asynchronous multi-agent execution pipeline
async function initiateOrchestration() {
    const query = document.getElementById("query-input").value.trim();
    if (!query) {
        alert("Please enter a strategic research objective query.");
        return;
    }

    const apiKey = document.getElementById("api-key-input").value.trim();
    const provider = document.getElementById("provider-select").value;

    // Auto-save API key to localStorage (and server) if provided
    if (apiKey) {
        localStorage.setItem("neuroweave_api_key", apiKey);
        localStorage.setItem("neuroweave_provider", provider);
        // Background save to server - don't await
        fetch("/api/save-key", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: apiKey, provider: provider })
        }).then(() => checkKeyStatus()).catch(() => {});
    }

    const executeBtn = document.getElementById("execute-btn");
    executeBtn.disabled = true;
    executeBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Organizing Agent Grid...`;

    // Clear UI structures
    document.getElementById("terminal-thought-stream").innerHTML = "";
    document.getElementById("svg-graph").innerHTML = "";
    document.getElementById("report-output-box").innerHTML = `
        <div class="report-placeholder">
            <i class="fa-solid fa-spinner fa-spin big-icon"></i>
            <h3>Synthesizing strategic report...</h3>
            <p>Subagents are currently executing tasks, scraping facts, and calculating values.</p>
        </div>
    `;

    try {
        const response = await fetch("/api/analyze", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                query: query,
                api_key: apiKey || null,
                provider: provider
            })
        });

        const data = await response.json();
        if (data.success) {
            activeSessionId = data.session_id;
            loggerSystemMessage(`Autonomous Orchestrator spawned pipeline: ${activeSessionId}`);
            // Establish SSE connection
            connectSSE(activeSessionId);
        } else {
            alert(`Error: ${data.message}`);
            executeBtn.disabled = false;
            executeBtn.innerHTML = `<i class="fa-solid fa-play"></i> Initiate Autonomous Loop`;
        }
    } catch (e) {
        alert(`Failed to talk to FastAPI backend: ${e}`);
        executeBtn.disabled = false;
        executeBtn.innerHTML = `<i class="fa-solid fa-play"></i> Initiate Autonomous Loop`;
    }
}

// Establishes Server-Sent Events stream connection to retrieve real-time state changes
function connectSSE(sessionId) {
    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource(`/api/stream/${sessionId}`);
    
    eventSource.onmessage = (event) => {
        const state = JSON.parse(event.data);
        updateDashboardUI(state);
    };

    eventSource.onerror = (e) => {
        console.log("SSE Connection concluded or timed out.", e);
        eventSource.close();
        document.getElementById("execute-btn").disabled = false;
        document.getElementById("execute-btn").innerHTML = `<i class="fa-solid fa-play"></i> Initiate Autonomous Loop`;
        loadSessionHistory();
    };
}

// Global UI Redraw Coordinator
function updateDashboardUI(state) {
    // 1. Update session badges & status
    const status = state.status.toUpperCase();
    const badge = document.getElementById("session-badge");
    badge.innerText = status;
    badge.className = "badge";
    if (status === "RUNNING") badge.classList.add("badge-planner");
    else if (status === "COMPLETED") badge.classList.add("badge-analyzer");
    else if (status === "REPLANNING") badge.classList.add("badge-critic");
    else if (status === "FAILED") badge.classList.add("badge-failed");
    else badge.classList.add("badge-system");

    // Dynamic execute button progression text & states
    const executeBtn = document.getElementById("execute-btn");
    if (status === "COMPLETED" || status === "FAILED" || status === "DEGRADED") {
        executeBtn.disabled = false;
        executeBtn.innerHTML = `<i class="fa-solid fa-play"></i> Initiate Autonomous Loop`;
    } else {
        const activeAgent = (state.active_agent || "").toLowerCase();
        let stepText = "Organizing Agent Grid...";
        if (activeAgent === "intent_analyzer") stepText = "1. Analyzing Intent...";
        else if (activeAgent === "planner") stepText = "2. Planning Task DAG...";
        else if (activeAgent === "researcher") stepText = "3. Gathering Web Insights...";
        else if (activeAgent === "analyzer") stepText = "4. Sandbox Calculations...";
        else if (activeAgent === "critic") stepText = "5. Auditing Code & Logic...";
        else if (activeAgent === "debate_engine") stepText = "6. Consensus Debate...";
        else if (activeAgent === "synthesizer") stepText = "7. Generating Report...";
        
        executeBtn.disabled = true;
        executeBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> ${stepText}`;
    }

    // 2. Render logs in stream terminal
    renderReasoningLogs(state.logs);

    // 3. Compute coordinates & Plot SVG Graph
    plotSvgGraph(state.tasks, state.active_agent);

    // 4. Gantt waterfall latencies chart
    plotLatencyWaterfall(state.traces || []);

    // 5. Update confidence metrics
    const avgConf = state.average_confidence || 0.00;
    document.getElementById("confidence-value").innerText = avgConf.toFixed(2);
    document.getElementById("confidence-bar").style.width = `${avgConf * 100}%`;

    // 6. Update telemetry metrics counters
    const metrics = state.metrics || {};
    document.getElementById("tel-model").innerText = state.active_agent.toUpperCase() || "N/A";
    document.getElementById("tel-tokens-in").innerText = metrics.total_input_tokens || 0;
    document.getElementById("tel-tokens-out").innerText = metrics.total_output_tokens || 0;
    document.getElementById("tel-cost").innerText = `$${(metrics.total_estimated_cost_usd || 0.0).toFixed(6)}`;
    
    const activeToolsCount = Object.values(metrics.tool_calls_summary || {}).reduce((a, b) => a + b, 0);
    document.getElementById("tel-tools").innerText = activeToolsCount;
    document.getElementById("tel-replans").innerText = metrics.replanning_cycle_count || 0;

    // 7. Render Strategic Report if completed
    const finalReport = state.working_memory ? state.working_memory.final_report : null;
    if (finalReport) {
        currentReportMd = finalReport;
        renderReportMarkdown(finalReport);
        // Switch tab to report automatically
        switchTab("report-tab");
    }
}

// Render Markdown report output natively
// Helper function to parse inline elements inside markdown text
function parseInlineMarkdown(text) {
    let result = text;
    // Bold
    result = result.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    // Italic
    result = result.replace(/\*(.*?)\*/g, "<em>$1</em>");
    // Links [text](url)
    result = result.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" class="report-link">$1</a>');
    // Inline superscript citation link pointing to the bibliography item anchor
    result = result.replace(/\[\^(\d+)\](?!\s*:)/g, '<a id="cite-link-$1" href="#cite-$1" class="citation-link"><sup class="citation-sup">[$1]</sup></a>');
    return result;
}

// Render Markdown report output natively with robust tables & active APA citations
function renderReportMarkdown(mdText) {
    const box = document.getElementById("report-output-box");
    if (!mdText) {
        box.innerHTML = "";
        return;
    }
    
    const lines = mdText.split(/\r?\n/);
    const htmlBlocks = [];
    
    let inTable = false;
    let tableRows = [];
    
    let inList = false;
    let listItems = [];
    
    function flushTable() {
        if (tableRows.length === 0) return;
        
        let tableHtml = '<div class="table-wrapper"><table>';
        
        // Determine if we have a table divider row (e.g. |---|---| or | :--- | ---: |)
        let hasDivider = false;
        if (tableRows.length > 1) {
            const secondRow = tableRows[1];
            hasDivider = secondRow.every(cell => /^[-\s:]+$/.test(cell) && cell.includes('-'));
        }
        
        let startIndex = 0;
        if (hasDivider) {
            // Compile first row as header elements
            tableHtml += '<thead><tr>';
            for (let cell of tableRows[0]) {
                tableHtml += `<th>${parseInlineMarkdown(cell)}</th>`;
            }
            tableHtml += '</tr></thead>';
            startIndex = 2; // Skip header row and formatting separator row
        }
        
        tableHtml += '<tbody>';
        for (let i = startIndex; i < tableRows.length; i++) {
            tableHtml += '<tr>';
            for (let cell of tableRows[i]) {
                tableHtml += `<td>${parseInlineMarkdown(cell)}</td>`;
            }
            tableHtml += '</tr>';
        }
        tableHtml += '</tbody></table></div>';
        
        htmlBlocks.push(tableHtml);
        tableRows = [];
        inTable = false;
    }
    
    function flushList() {
        if (listItems.length === 0) return;
        let listHtml = '<ul>';
        for (let item of listItems) {
            listHtml += `<li>${parseInlineMarkdown(item)}</li>`;
        }
        listHtml += '</ul>';
        htmlBlocks.push(listHtml);
        listItems = [];
        inList = false;
    }
    
    for (let line of lines) {
        const trimmed = line.trim();
        
        // 1. Table Row Check
        if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
            if (inList) flushList();
            inTable = true;
            // Slice the bounding pipes and map individual cells
            const cells = line.split("|").slice(1, -1).map(c => c.trim());
            tableRows.push(cells);
            continue;
        } else if (inTable) {
            flushTable();
        }
        
        // 2. Unordered List Check
        if (trimmed.startsWith("- ")) {
            if (inTable) flushTable();
            inList = true;
            listItems.push(trimmed.substring(2).trim());
            continue;
        } else if (inList) {
            flushList();
        }
        
        // 3. Blank/Empty Spacer lines
        if (trimmed === "") {
            continue;
        }
        
        // 4. Heading Blocks
        if (trimmed.startsWith("# ")) {
            htmlBlocks.push(`<h1>${parseInlineMarkdown(trimmed.substring(2).trim())}</h1>`);
            continue;
        }
        if (trimmed.startsWith("## ")) {
            htmlBlocks.push(`<h2>${parseInlineMarkdown(trimmed.substring(3).trim())}</h2>`);
            continue;
        }
        if (trimmed.startsWith("### ")) {
            htmlBlocks.push(`<h3>${parseInlineMarkdown(trimmed.substring(4).trim())}</h3>`);
            continue;
        }
        
        // 5. APA Bibliography Definition Check: [^index]: content
        const bibMatch = trimmed.match(/^\[\^(\d+)\]:\s*(.*)$/);
        if (bibMatch) {
            const index = bibMatch[1];
            const content = bibMatch[2];
            htmlBlocks.push(`<div id="cite-${index}" class="bibliography-item"><a href="#cite-link-${index}" class="backlink" title="Jump back to source citation"><sup class="citation-sup">[${index}]</sup></a> ${parseInlineMarkdown(content)}</div>`);
            continue;
        }
        
        // 6. Generic Paragraph wrapping fallback
        htmlBlocks.push(`<p>${parseInlineMarkdown(trimmed)}</p>`);
    }
    
    // Flush remaining components
    if (inTable) flushTable();
    if (inList) flushList();
    
    box.innerHTML = htmlBlocks.join("\n");
}

// Helper function to wrap SVG text to prevent clashing
function wrapSvgText(textElement, text, x, y, maxChars = 16) {
    const words = text.split(' ');
    let line = '';
    let lines = [];
    
    for (let n = 0; n < words.length; n++) {
        let testLine = line + words[n] + ' ';
        if (testLine.length > maxChars && n > 0) {
            lines.push(line.trim());
            line = words[n] + ' ';
        } else {
            line = testLine;
        }
    }
    lines.push(line.trim());
    
    // Clear original content
    textElement.textContent = '';
    
    // Position lines so that the bottom of the text block aligns exactly to y (no overlaps with circle)
    const lineHeight = 12; // px
    const totalHeight = lines.length * lineHeight;
    const startY = y - totalHeight + lineHeight;
    
    lines.forEach((lineText, index) => {
        const tspan = document.createElementNS("http://www.w3.org/2000/svg", "tspan");
        tspan.setAttribute("x", x);
        tspan.setAttribute("y", startY + (index * lineHeight));
        tspan.textContent = lineText;
        textElement.appendChild(tspan);
    });
}

// Plots Directed Acyclic Graph (DAG) task nodes onto dynamic SVG canvas
function plotSvgGraph(tasks, activeAgent) {
    const svg = document.getElementById("svg-graph");
    svg.innerHTML = ""; // Clear active canvas

    const taskList = Object.values(tasks);
    if (taskList.length === 0) return;

    // Emojis representing active subagent roles
    const emojiMap = {
        'planner': '🧭',
        'researcher': '🕵️',
        'analyzer': '🧮',
        'critic': '⚖️',
        'intent_analyzer': '🤖'
    };

    // 1. Group tasks by hierarchical columns/layers using dependency counting
    const layers = {};
    const taskCoords = {};

    // Topological horizontal separation layers mapping
    taskList.forEach(task => {
        let depth = 0;
        // Count dependencies recursively
        const countDepth = (tId) => {
            const t = tasks[tId];
            if (!t || !t.dependencies || t.dependencies.length === 0) return 0;
            return 1 + Math.max(...t.dependencies.map(countDepth));
        };
        depth = countDepth(task.id);
        
        if (!layers[depth]) layers[depth] = [];
        layers[depth].push(task);
    });

    const layerKeys = Object.keys(layers).sort((a,b) => a-b);
    const canvasWidth = svg.clientWidth || 600;
    const canvasHeight = svg.clientHeight || 450;

    // Use a clean, margins-aware layer distribution
    const marginX = 80;
    const availableWidth = canvasWidth - 2 * marginX;
    const layerWidth = layerKeys.length > 1 ? availableWidth / (layerKeys.length - 1) : availableWidth;

    // 2. Programmatically calculate Cartesian coordinates
    layerKeys.forEach((layerKey, lIndex) => {
        const layerTasks = layers[layerKey];
        const cx = layerKeys.length > 1 ? marginX + lIndex * layerWidth : marginX + availableWidth / 2;
        
        const totalRows = layerTasks.length;
        const rowHeight = canvasHeight / (totalRows + 1);

        layerTasks.forEach((task, rIndex) => {
            const cy = rowHeight * (rIndex + 1);
            taskCoords[task.id] = { x: cx, y: cy };
        });
    });

    // 3. Draw Connecting Edge Arrows (truncated to circle boundary)
    taskList.forEach(task => {
        const target = taskCoords[task.id];
        task.dependencies.forEach(depId => {
            const source = taskCoords[depId];
            if (source && target) {
                const dx = target.x - source.x;
                const dy = target.y - source.y;
                const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                
                const r = 24; // Node Circle Radius
                // Offset start/end coordinate values by circle radius to stop exactly at boundaries
                const x1 = source.x + (r * dx) / dist;
                const y1 = source.y + (r * dy) / dist;
                const x2 = target.x - (r * dx) / dist;
                const y2 = target.y - (r * dy) / dist;

                const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
                line.setAttribute("x1", x1);
                line.setAttribute("y1", y1);
                line.setAttribute("x2", x2);
                line.setAttribute("y2", y2);
                
                // Color code line state
                line.setAttribute("class", `edge-line edge-${task.status}`);
                if (task.status === "running") {
                    line.setAttribute("stroke", "#4f46e5");
                }
                
                line.setAttribute("marker-end", task.status === "failed" ? "url(#arrow-failed)" : "url(#arrow)");
                svg.appendChild(line);
            }
        });
    });

    // 4. Draw Interactive Glow Circles & Node Labels
    taskList.forEach(task => {
        const coord = taskCoords[task.id];
        if (!coord) return;

        const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
        group.setAttribute("class", "node-group");
        
        // Dynamic pulsators for active nodes
        if (task.status === "running" || (activeAgent === task.assigned_agent && task.status === "running")) {
            const glow = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            glow.setAttribute("cx", coord.x);
            glow.setAttribute("cy", coord.y);
            glow.setAttribute("r", 30);
            glow.setAttribute("class", "node-glow");
            glow.setAttribute("fill", "#8b5cf6");
            glow.setAttribute("opacity", 0.4);
            group.appendChild(glow);
        }

        // Central circle representing task entity
        const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        circle.setAttribute("cx", coord.x);
        circle.setAttribute("cy", coord.y);
        circle.setAttribute("r", 24);
        circle.setAttribute("class", `node-circle node-${task.status}`);
        group.appendChild(circle);

        // Draw subagent emoji inside circle
        const agentName = (task.assigned_agent || '').toLowerCase();
        const emoji = emojiMap[agentName] || '🤖';
        const emojiText = document.createElementNS("http://www.w3.org/2000/svg", "text");
        emojiText.setAttribute("x", coord.x);
        emojiText.setAttribute("y", coord.y + 5);
        emojiText.setAttribute("class", "node-emoji");
        emojiText.setAttribute("text-anchor", "middle");
        emojiText.setAttribute("font-size", "16px");
        emojiText.textContent = emoji;
        group.appendChild(emojiText);

        // Task label text (wrapped to prevent clashing)
        const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
        text.setAttribute("x", coord.x);
        text.setAttribute("class", "node-text");
        wrapSvgText(text, task.title, coord.x, coord.y - 32);
        group.appendChild(text);

        // Agent badge label text (shifted lower)
        const agentText = document.createElementNS("http://www.w3.org/2000/svg", "text");
        agentText.setAttribute("x", coord.x);
        agentText.setAttribute("y", coord.y + 36);
        agentText.setAttribute("class", "node-agent-text");
        agentText.textContent = task.assigned_agent.toUpperCase();
        group.appendChild(agentText);

        svg.appendChild(group);
    });
}

// Renders the waterfall Gantt timelines
function plotLatencyWaterfall(traces) {
    const container = document.getElementById("timeline-waterfall-box");
    if (traces.length === 0) {
        container.innerHTML = `<div class="empty-list-placeholder">No trace timings parsed yet.</div>`;
        return;
    }

    container.innerHTML = "";
    
    // Sort spans by start times
    const sorted = [...traces].sort((a,b) => a.start_time - b.start_time);
    
    const minStart = sorted[0].start_time;
    const maxEnd = Math.max(...sorted.map(s => s.start_time + s.duration_sec));
    const totalDuration = maxEnd - minStart || 1.0;

    sorted.forEach(span => {
        const leftPercent = ((span.start_time - minStart) / totalDuration) * 100;
        const widthPercent = (span.duration_sec / totalDuration) * 100;

        const row = document.createElement("div");
        row.className = "gantt-row";
        row.innerHTML = `
            <div class="gantt-label">
                <span>${span.name} (${span.agent})</span>
                <span>${span.duration_sec.toFixed(2)}s</span>
            </div>
            <div class="gantt-track">
                <div class="gantt-bar gantt-bar-${span.agent}" style="left: ${leftPercent}%; width: ${Math.max(widthPercent, 2)}%"></div>
            </div>
        `;
        container.appendChild(row);
    });
}

// Render real-time scrolling thought logs
function renderReasoningLogs(logs) {
    const terminal = document.getElementById("terminal-thought-stream");
    terminal.innerHTML = ""; // Redraw sequentially to match indices

    logs.forEach(log => {
        const row = document.createElement("div");
        row.className = `log-entry log-${log.type}`;
        
        // Format relative timestamp
        const timeStr = new Date(log.timestamp * 1000).toTimeString().split(' ')[0].substring(3);
        
        row.innerHTML = `
            <div class="log-header" style="display:flex; justify-content:space-between;">
                <span class="log-badge ${log.agent}-badge">${log.agent.toUpperCase()}</span>
                <span class="log-time">[${timeStr}]</span>
            </div>
            <div class="log-text">${log.message}</div>
        `;
        terminal.appendChild(row);
    });
    
    // Keep scrolled downwards
    terminal.scrollTop = terminal.scrollHeight;
}

// System logging fallbacks
function loggerSystemMessage(msg) {
    const terminal = document.getElementById("terminal-thought-stream");
    const row = document.createElement("div");
    row.className = `log-entry log-info`;
    row.innerHTML = `
        <div class="log-header">
            <span class="log-badge system-badge">SYSTEM</span>
        </div>
        <div class="log-text">${msg}</div>
    `;
    terminal.appendChild(row);
    terminal.scrollTop = terminal.scrollHeight;
}

// File Upload Handler (ingests docs to vector store)
async function handleFileUpload(file) {
    if (!file) return;
    
    const statusBox = document.getElementById("upload-status");
    statusBox.innerText = `Parsing ${file.name}...`;
    statusBox.style.color = "#8b5cf6";

    const formData = new FormData();
    formData.append("file", file);
    
    const apiKey = document.getElementById("api-key-input").value.trim();
    if (apiKey) {
        formData.append("api_key", apiKey);
    }

    try {
        const response = await fetch("/api/upload", {
            method: "POST",
            body: formData
        });
        const data = await response.json();
        
        if (data.success) {
            statusBox.innerText = `Successfully indexed: ${file.name}`;
            statusBox.style.color = "#10b981";
            loggerSystemMessage(`Ingested semantic asset: ${file.name}`);
        } else {
            statusBox.innerText = `Upload failed: ${data.detail}`;
            statusBox.style.color = "#ef4444";
        }
    } catch (e) {
        statusBox.innerText = `Connection failed: ${e}`;
        statusBox.style.color = "#ef4444";
    }
}

// Download markdown strategic report locally
function downloadReport() {
    if (!currentReportMd) {
        alert("No synthesized strategic report exists to download.");
        return;
    }
    const blob = new Blob([currentReportMd], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `neuroweave_strategic_report_${activeSessionId || 'session'}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

// Pulls historical sessions compiled from server SQLite storage
async function loadSessionHistory() {
    const list = document.getElementById("session-history-list");
    try {
        const res = await fetch("/api/sessions");
        const data = await res.json();
        const sessions = data.sessions || [];
        
        if (sessions.length === 0) {
            list.innerHTML = `<div class="empty-list-placeholder">No historical strategic report compiled yet.</div>`;
            return;
        }

        list.innerHTML = "";
        sessions.forEach(sess => {
            const item = document.createElement("div");
            item.className = "history-item";
            item.innerHTML = `
                <span class="history-query" title="${sess.query}">${sess.query}</span>
                <span class="badge ${sess.status === 'completed' ? 'badge-analyzer' : 'badge-system'}">${sess.status}</span>
            `;
            // Bind click to load report archive
            item.addEventListener("click", () => loadReportArchive(sess.session_id));
            list.appendChild(item);
        });
    } catch (e) {
        console.error("Error loading histories: ", e);
    }
}

// Reloads a completed historical report from SQLite to the UI
async function loadReportArchive(sessionId) {
    try {
        const res = await fetch(`/api/report/${sessionId}`);
        if (res.status === 200) {
            const data = await res.json();
            activeSessionId = sessionId;
            currentReportMd = data.content;
            renderReportMarkdown(data.content);
            
            // Switch tabs
            switchTab("report-tab");
            
            // Clear SVGs or timers since this represents static history
            document.getElementById("svg-graph").innerHTML = `
                <div class="report-placeholder">
                    <h3>Displaying archived static query session</h3>
                    <p>ID: ${sessionId}</p>
                </div>
            `;
            document.getElementById("session-badge").innerText = "ARCHIVED";
            loggerSystemMessage(`Loaded archived report session: ${sessionId}`);
        } else {
            alert("Could not load report details.");
        }
    } catch (e) {
        alert(`Error reloading history: ${e}`);
    }
}

// Applies quick-action templates in the sidebar
function applyTemplate(type) {
    const input = document.getElementById("query-input");
    if (!input) return;

    let queryText = "";
    if (type === "startups") {
        queryText = "Build me a market analysis for AI automation startups in India";
    } else if (type === "finance") {
        queryText = "Calculate capitalization models for Series A valuation seed rounds";
    } else if (type === "replan") {
        queryText = "Force critic replanning test to evaluate DAG expansion recovery";
    }

    input.value = queryText;
    loggerSystemMessage(`Applied quick research template: "${queryText}"`);
    initiateOrchestration();
}

