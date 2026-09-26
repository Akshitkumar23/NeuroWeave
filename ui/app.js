// ─── STATE ──────────────────────────────────────────────────────
let activeSessionId = null;
let eventSource     = null;
let currentReportMd = "";
let logCount        = 0;
let logsOpen        = false;
let selectedDivision = "auto";
let speechRecognitionInstance = null;
let isSpeechRecording = false;
window.activeChartInstances = [];
window.latestTasks = {};
window.latestTraces = [];
window.latestPersona = null;
window.latestPersonaMeta = null;
window.latestSkills = [];

// ─── INIT ────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    // Run Button listener
    const execBtn = document.getElementById("execute-btn");
    if (execBtn) {
        execBtn.addEventListener("click", (e) => {
            e.preventDefault();
            triggerWorkflow();
        });
    }

    // Drop zone handling
    const dropZone  = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");
    if (dropZone && fileInput) {
        dropZone.addEventListener("click", () => fileInput.click());
        fileInput.addEventListener("change", (e) => handleFileUpload(e.target.files[0]));
        dropZone.addEventListener("dragover",  (e) => { e.preventDefault(); dropZone.style.borderColor = "#6366f1"; });
        dropZone.addEventListener("dragleave", ()  => { dropZone.style.borderColor = ""; });
        dropZone.addEventListener("drop", (e) => {
            e.preventDefault();
            dropZone.style.borderColor = "";
            if (e.dataTransfer.files.length > 0) handleFileUpload(e.dataTransfer.files[0]);
        });
    }

    // Enter key triggers analysis in textarea (Ctrl+Enter or Cmd+Enter)
    const queryInput = document.getElementById("query-input");
    if (queryInput) {
        queryInput.addEventListener("keydown", (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                triggerWorkflow();
            }
        });
    }

    // Global keyboard listener for modal
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            closeNodeInspector();
        }
    });

    // Load session history
    loadSessionHistory();

    // Restore saved credentials
    const savedKey      = localStorage.getItem("neuroweave_api_key");
    const savedProvider = localStorage.getItem("neuroweave_provider") || "gemini";
    if (savedKey) {
        const keyInput = document.getElementById("api-key-input");
        if (keyInput) keyInput.value = savedKey;
        const provSelect = document.getElementById("provider-select");
        if (provSelect) provSelect.value = savedProvider;
    }

    checkKeyStatus();
});

// ─── DIVISION SELECTOR ───────────────────────────────────────────
function setDivision(divName) {
    selectedDivision = divName;
    document.querySelectorAll(".div-pill").forEach(btn => {
        if (btn.getAttribute("data-div") === divName) {
            btn.classList.add("active");
        } else {
            btn.classList.remove("active");
        }
    });
    const telPersona = document.getElementById("tel-persona");
    if (telPersona) {
        telPersona.textContent = divName === "auto" ? "Auto" : divName.charAt(0).toUpperCase() + divName.slice(1);
    }
}

// ─── QUICK STARTER PROMPT SETTER ─────────────────────────────────
function setQuery(text) {
    const input = document.getElementById("query-input");
    if (input) {
        input.value = text;
        input.focus();
    }
}

// ─── LOGS SIDEBAR TOGGLE ─────────────────────────────────────────
function toggleLogs() {
    const sidebar  = document.getElementById("logs-sidebar");
    const overlay  = document.getElementById("logs-overlay");
    const notif    = document.getElementById("logs-notif");
    logsOpen = !logsOpen;
    if (sidebar) sidebar.classList.toggle("open", logsOpen);
    if (overlay) overlay.style.display = logsOpen ? "block" : "none";
    if (logsOpen && notif) notif.style.display = "none";
}

// ─── SECTION COLLAPSE ────────────────────────────────────────────
function toggleSection(bodyId) {
    const body  = document.getElementById(bodyId);
    if (!body) return;
    const arrow = body.previousElementSibling
                      ? body.previousElementSibling.querySelector(".toggle-icon")
                      : null;
    body.classList.toggle("hidden");
    if (arrow) arrow.style.transform = body.classList.contains("hidden") ? "rotate(0deg)" : "rotate(180deg)";
}

// ─── TAB SWITCHING ───────────────────────────────────────────────
function switchTab(tabId) {
    document.querySelectorAll(".tab-pane").forEach(p => p.classList.add("hidden"));
    document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
    const target = document.getElementById(tabId);
    if (target) target.classList.remove("hidden");
    
    const tabMap = { 
        "graph-tab": "tab-btn-graph", 
        "report-tab": "tab-btn-report", 
        "timeline-tab": "tab-btn-timeline",
        "evidence-tab": "tab-btn-evidence"
    };
    const btn = document.getElementById(tabMap[tabId]);
    if (btn) btn.classList.add("active");

    if (tabId === "graph-tab" && window.latestTasks) {
        plotGraph(window.latestTasks, window.latestActiveAgent);
    } else if (tabId === "evidence-tab" && activeSessionId) {
        renderEvidenceInspector(activeSessionId);
    }
}


// ─── KEY STATUS CHECK ────────────────────────────────────────────
async function checkKeyStatus() {
    try {
        const badge = document.getElementById("api-mode-badge");
        if (!badge) return;
        badge.className = "api-badge api-sim";
        badge.innerHTML = `<i class="fa-solid fa-shield-halved"></i> NEUROWEAVE MODE: ZERO-API`;
        badge.style.color = "#38bdf8";
    } catch(e) { console.log("Key status error:", e); }
}

function handleProviderChange() {
    const provSelect = document.getElementById("provider-select");
    if (!provSelect) return;
    const provider = provSelect.value;
    const keyInput = document.getElementById("api-key-input");
    const saveBtn = document.querySelector(".btn-save");
    
    if (provider === "ollama") {
        if (keyInput) keyInput.style.display = "none";
        if (saveBtn) saveBtn.style.display = "none";
    } else {
        if (keyInput) keyInput.style.display = "block";
        if (saveBtn) saveBtn.style.display = "inline-flex";
    }
}

// ─── SAVE API KEY ────────────────────────────────────────────────
async function saveApiKey() {
    const keyInput = document.getElementById("api-key-input");
    const apiKey   = keyInput ? keyInput.value.trim() : "";
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
    } catch(e) { console.error("Save key error:", e); }
}

// ─── SET STATUS PILL ─────────────────────────────────────────────
function setStatus(type, text) {
    const pill = document.getElementById("status-pill");
    const span = document.getElementById("status-text");
    if (!pill || !span) return;
    pill.className = `status-pill status-${type}`;
    span.textContent = text;
}

// ─── TRIGGER AUTONOMOUS WORKFLOW ─────────────────────────────────
async function triggerWorkflow() {
    const queryEl  = document.getElementById("query-input");
    const query    = queryEl ? queryEl.value.trim() : "";
    const keyInput = document.getElementById("api-key-input");
    const apiKey   = keyInput ? keyInput.value.trim() : "";
    const provEl   = document.getElementById("provider-select");
    const provider = provEl ? provEl.value : "gemini";

    if (!query) {
        alert("Please enter a research objective.");
        if (queryEl) queryEl.focus();
        return;
    }

    // Reset Stream and Log state
    logCount = 0;
    const badge = document.getElementById("log-count-badge");
    if (badge) badge.textContent = "0";
    const stream = document.getElementById("terminal-thought-stream");
    if (stream) stream.innerHTML = "";

    // Reset active skills
    renderActiveSkills([]);

    // Clear main panels
    const svgGraph = document.getElementById("svg-graph");
    if (svgGraph) {
        svgGraph.innerHTML = `
            <text x="50%" y="50%" text-anchor="middle" fill="rgba(255,255,255,0.2)"
                font-size="14" font-family="Inter">Formulating autonomous execution DAG...</text>`;
    }
    const reportBox = document.getElementById("report-output-box");
    if (reportBox) {
        reportBox.innerHTML = `
            <div class="report-empty-state">
                <div class="empty-icon-box">
                    <i class="fa-solid fa-spinner fa-spin" style="color:#6366f1"></i>
                </div>
                <h3>Synthesizing Publication-Grade Strategic Report...</h3>
                <p>Autonomous agents are conducting multi-angle web research, quantitative sandbox calculations, and fact-checking audits.</p>
            </div>`;
    }

    const btn = document.getElementById("execute-btn");
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>Executing Multi-Agent Workflow...</span>`;
    }
    setStatus("running", "RUNNING — Multi-Agent NEXUS Active");

    // Notification on logs
    const notif = document.getElementById("logs-notif");
    if (notif) notif.style.display = "block";

    try {
        const res  = await fetch("/api/analyze", {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify({
                query,
                api_key: apiKey || null,
                provider,
                division: selectedDivision
            })
        });
        const data = await res.json();
        if (data.success) {
            activeSessionId = data.session_id;
            appendLog("system", "SYSTEM", `Pipeline initiated — Session ID: ${activeSessionId}`);
            switchTab("graph-tab");
            connectSSE(activeSessionId);
        } else {
            alert(`Error starting pipeline: ${data.message}`);
            resetRunBtn();
            setStatus("error", "ERROR — Initiation Failed");
        }
    } catch(e) {
        alert(`Server connection failure: ${e}`);
        resetRunBtn();
        setStatus("error", "ERROR — Connection Failed");
    }
}

function resetRunBtn() {
    const btn = document.getElementById("execute-btn");
    if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-bolt"></i> <span>Run Analysis</span> <kbd class="kbd-hint">Ctrl ↵</kbd>`;
    }
}

// ─── SSE CONNECTION ──────────────────────────────────────────────
function connectSSE(sessionId) {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    eventSource = new EventSource(`/api/stream/${sessionId}`);
    eventSource.onmessage = (e) => {
        try {
            const state = JSON.parse(e.data);
            updateUI(state);
            const status = (state.status || "").toLowerCase();
            if (status === "completed" || status === "failed" || status === "degraded") {
                console.log(`[SSE] Terminal status '${status}' reached. Closing stream cleanly.`);
                if (eventSource) {
                    eventSource.close();
                    eventSource = null;
                }
                resetRunBtn();
                loadSessionHistory();
            }
        } catch (err) {
            console.debug("[SSE] State parse or ping received:", err);
        }
    };
    eventSource.onerror = () => {
        if (eventSource) {
            const wasClosed = eventSource.readyState === EventSource.CLOSED;
            eventSource.close();
            eventSource = null;
            if (!wasClosed) {
                console.debug("[SSE] Connection ended or closed by server.");
            }
        }
        resetRunBtn();
        loadSessionHistory();
    };
}

// ─── MAIN UI UPDATE ──────────────────────────────────────────────
function updateUI(state) {
    const status      = (state.status || "").toLowerCase();
    const activeAgent = (state.active_agent || "").toLowerCase();

    // Status pill
    const done = status === "completed" || status === "degraded";
    const fail = status === "failed";
    if (done)       setStatus("done",    "DONE — Executive Report Ready");
    else if (fail)  setStatus("error",   "ERROR — Workflow Failed");
    else            setStatus("running", `RUNNING — ${agentLabel(activeAgent)}`);

    // Run button
    if (done || fail) {
        resetRunBtn();
    } else {
        const btn = document.getElementById("execute-btn");
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>${agentLabel(activeAgent)}</span>`;
        }
    }

    // Store state in window for inspector and DAG synchronization
    window.latestTasks = state.tasks || {};
    window.latestTraces = state.traces || [];
    window.latestPersona = state.assigned_persona || null;
    window.latestPersonaMeta = state.persona_meta || null;
    window.latestSkills = state.active_skills || [];

    // Logs
    renderLogs(state.logs || []);

    // Active skills & Agency Specialist Persona
    renderActiveSkills(state.active_skills || [], state.assigned_persona, state.persona_meta);

    // Graph
    plotGraph(state.tasks || {}, activeAgent);

    // Timeline
    plotTimeline(state.traces || []);

    // Confidence
    const conf = state.average_confidence || 0;
    const confBar = document.getElementById("confidence-bar");
    if (confBar) confBar.style.width = `${conf * 100}%`;
    const confVal = document.getElementById("confidence-value");
    if (confVal) confVal.textContent = conf.toFixed(2);

    // Telemetry footer
    const m = state.metrics || {};
    const telModel = document.getElementById("tel-model");
    if (telModel) telModel.textContent = activeAgent ? activeAgent.toUpperCase() : "—";
    
    const telPersona = document.getElementById("tel-persona");
    if (telPersona) {
        if (state.assigned_persona) {
            telPersona.textContent = state.assigned_persona;
        } else if (selectedDivision !== "auto") {
            telPersona.textContent = selectedDivision.toUpperCase();
        }
    }

    const telIn = document.getElementById("tel-tokens-in");
    if (telIn) telIn.textContent = m.total_input_tokens || 0;
    const telOut = document.getElementById("tel-tokens-out");
    if (telOut) telOut.textContent = m.total_output_tokens || 0;
    const telCost = document.getElementById("tel-cost");
    if (telCost) telCost.textContent = `$${(m.total_estimated_cost_usd || 0).toFixed(6)}`;
    const telReplans = document.getElementById("tel-replans");
    if (telReplans) telReplans.textContent = m.replanning_cycle_count || 0;
    const toolsTotal = Object.values(m.tool_calls_summary || {}).reduce((a,b) => a+b, 0);
    const telTools = document.getElementById("tel-tools");
    if (telTools) telTools.textContent = toolsTotal;

    // Report
    const report = state.working_memory ? state.working_memory.final_report : null;
    if (report) {
        currentReportMd = report;
        renderReport(report);
        switchTab("report-tab");

        const metaHeader = document.getElementById("report-meta-header");
        if (metaHeader) metaHeader.style.display = "flex";
        const metaSess = document.getElementById("meta-session-id");
        if (metaSess) metaSess.textContent = `Session: ${activeSessionId ? activeSessionId.slice(0,8) : "—"}`;
        const metaConf = document.getElementById("meta-confidence");
        if (metaConf) metaConf.textContent = `Audit Score: ${conf.toFixed(2)} / 1.00`;
        const metaPers = document.getElementById("meta-persona");
        if (metaPers) metaPers.textContent = `Specialist: ${state.assigned_persona || "Research Synthesist"}`;

        // Automatically fetch and populate evidence inspector tab
        if (activeSessionId) {
            renderEvidenceInspector(activeSessionId);
        }
    }

    // Phase 5: Live Stepper, Pod Visualizer, and Telemetry Updates
    updateExecutiveStepper(state);
    updateAgencyPodVisualizer(state);
    updateTelemetryStats(state);
}

// ─── PHASE 5: EXECUTIVE RESEARCH JOURNEY STEPPER ──────────────────
function updateExecutiveStepper(state) {
    const status = (state.status || "").toLowerCase();
    const activeAgent = (state.active_agent || "").toLowerCase();
    const isDone = status === "completed" || status === "degraded";
    const isFail = status === "failed";

    const steps = [
        { id: "step-query",         agent: "init",             label: "Query Submitted" },
        { id: "step-understanding", agent: "intent_analyzer",  label: "Classifying Intent & Entities" },
        { id: "step-pod",           agent: "planner",          label: "Matching Agency Pod & Specialists" },
        { id: "step-research",      agent: "researcher",       label: "Harvesting Real Empirical Evidence" },
        { id: "step-analysis",      agent: "analyzer",         label: "Executing Python Sandbox Calculations" },
        { id: "step-critic",        agent: "critic",           label: "NEXUS Epistemic Red-Green Audit" },
        { id: "step-debate",        agent: "debate_engine",    label: "Dialectical Counter-Factual Debate" },
        { id: "step-gate",          agent: "quality_gate",     label: "Evaluating Autonomous Quality Gates" },
        { id: "step-dossier",       agent: "synthesizer",      label: "Synthesizing Final Publication Dossier" }
    ];

    const agentOrder = ["init", "intent_analyzer", "planner", "researcher", "analyzer", "critic", "debate_engine", "quality_gate", "synthesizer"];
    let currentIdx = isDone ? 9 : agentOrder.indexOf(activeAgent);
    if (currentIdx === -1) currentIdx = 1;

    steps.forEach((s, idx) => {
        const el = document.getElementById(s.id);
        const conn = document.getElementById(`conn-${idx}`);
        if (!el) return;

        el.classList.remove("completed", "running", "failed", "replanned");
        if (conn) conn.classList.remove("completed");

        if (isDone) {
            el.classList.add("completed");
            if (conn) conn.classList.add("completed");
        } else if (isFail && idx === currentIdx) {
            el.classList.add("failed");
        } else if (idx < currentIdx) {
            el.classList.add("completed");
            if (conn) conn.classList.add("completed");
        } else if (idx === currentIdx) {
            el.classList.add("running");
        }
    });

    // Check for replanning indicator
    const replans = (state.metrics && state.metrics.replanning_cycle_count) || 0;
    if (replans > 0 && !isDone) {
        const gateEl = document.getElementById("step-gate");
        if (gateEl) gateEl.classList.add("replanned");
    }

    const msgEl = document.getElementById("stepper-status-msg");
    if (msgEl) {
        if (isDone) {
            msgEl.textContent = "Stage 9/9 [FINAL DOSSIER]: Publication dossier finalized with auditable claim-level provenance.";
        } else if (isFail) {
            msgEl.textContent = "Execution halted due to system constraint.";
        } else {
            const stepNum = Math.min(currentIdx + 1, 9);
            const curStep = steps[Math.min(currentIdx, 8)];
            msgEl.textContent = `Stage ${stepNum}/9 [${curStep.id.replace("step-","").toUpperCase()}]: ${curStep.label}...`;
        }
    }
}

// ─── PHASE 5: LIVE AGENCY POD VISUALIZER ──────────────────────────
function updateAgencyPodVisualizer(state) {
    const podContainer = document.getElementById("pod-visualizer");
    if (!podContainer) return;

    let pod = null;
    if (state.working_memory && state.working_memory.agency_pod) {
        pod = state.working_memory.agency_pod;
    }

    // Try extracting from report markdown if not in working memory object
    const reportText = (state.working_memory && state.working_memory.final_report) || currentReportMd || "";
    let division = pod ? pod.division : "";
    let leadName = pod && pod.lead_persona ? pod.lead_persona.name : "";
    let leadRole = pod && pod.lead_persona ? pod.lead_persona.role : "";
    let leadTools = pod && pod.lead_persona && pod.lead_persona.bound_tools ? pod.lead_persona.bound_tools.slice(0, 3).join(", ") : "web_search, python_sandbox";

    let sup1Name = (pod && pod.supporting_personas && pod.supporting_personas[0]) ? pod.supporting_personas[0].name : "";
    let sup1Role = (pod && pod.supporting_personas && pod.supporting_personas[0]) ? pod.supporting_personas[0].role : "Technical Specialist";
    let sup1Tools = (pod && pod.supporting_personas && pod.supporting_personas[0] && pod.supporting_personas[0].bound_tools) ? pod.supporting_personas[0].bound_tools.slice(0, 2).join(", ") : "domain_analyzer";

    let sup2Name = (pod && pod.supporting_personas && pod.supporting_personas[1]) ? pod.supporting_personas[1].name : "";
    let sup2Role = (pod && pod.supporting_personas && pod.supporting_personas[1]) ? pod.supporting_personas[1].role : "Operational Auditor";
    let sup2Tools = (pod && pod.supporting_personas && pod.supporting_personas[1] && pod.supporting_personas[1].bound_tools) ? pod.supporting_personas[1].bound_tools.slice(0, 2).join(", ") : "python_sandbox";

    if (!leadName && reportText) {
        const podMatch = reportText.match(/🏛️ \*\*AGENCY DIVISION POD: (.*?)\*\*/);
        if (podMatch) division = podMatch[1];

        const leadMatch = reportText.match(/\*\*Lead Specialist:\*\* (.*?) \(\*(.*?)\*\)/);
        if (leadMatch) {
            leadName = leadMatch[1];
            leadRole = leadMatch[2];
        }

        const supMatch = reportText.match(/Supporting Specialists: (.*?)(?: \||\n)/);
        if (supMatch) {
            const sups = supMatch[1].split(",").map(s => s.trim());
            if (sups[0]) sup1Name = sups[0];
            if (sups[1]) sup2Name = sups[1];
        }
    }

    if (!leadName && state.assigned_persona) {
        leadName = state.assigned_persona;
        leadRole = (state.persona_meta && state.persona_meta.role) || "Principal Specialist";
        division = (state.persona_meta && state.persona_meta.division) || "Architecture";
    }

    if (leadName) {
        podContainer.style.display = "block";
        const divLabel = document.getElementById("pod-division-label");
        if (divLabel) divLabel.textContent = `Agency Division: ${division || "Architecture"}`;

        // Report mode tag
        let mode = "TECHNICAL";
        const modeMatch = reportText.match(/🏷️ \*\*REPORT MODE: (.*?)\*\*/);
        if (modeMatch) mode = modeMatch[1];
        const modeTag = document.getElementById("pod-report-mode-tag");
        if (modeTag) modeTag.textContent = `MODE: ${mode}`;

        // Lead Card
        const lNameEl = document.getElementById("pod-lead-name");
        if (lNameEl) lNameEl.textContent = leadName;
        const lRoleEl = document.getElementById("pod-lead-role");
        if (lRoleEl) lRoleEl.textContent = leadRole;
        const lToolsEl = document.getElementById("pod-lead-tools");
        if (lToolsEl) {
            lToolsEl.innerHTML = leadTools.split(",").map(t => `<span class="tool-tag"><i class="fa-solid fa-wrench"></i> ${escHtml(t.trim())}</span>`).join(" ");
        }

        // Supporting 1 Card
        const s1NameEl = document.getElementById("pod-sup1-name");
        if (s1NameEl) s1NameEl.textContent = sup1Name || "Domain Specialist";
        const s1RoleEl = document.getElementById("pod-sup1-role");
        if (s1RoleEl) s1RoleEl.textContent = sup1Role;
        const s1ToolsEl = document.getElementById("pod-sup1-tools");
        if (s1ToolsEl) {
            s1ToolsEl.innerHTML = sup1Tools.split(",").map(t => `<span class="tool-tag"><i class="fa-solid fa-screwdriver-wrench"></i> ${escHtml(t.trim())}</span>`).join(" ");
        }

        // Supporting 2 Card
        const s2NameEl = document.getElementById("pod-sup2-name");
        if (s2NameEl) s2NameEl.textContent = sup2Name || "Operational Auditor";
        const s2RoleEl = document.getElementById("pod-sup2-role");
        if (s2RoleEl) s2RoleEl.textContent = sup2Role;
        const s2ToolsEl = document.getElementById("pod-sup2-tools");
        if (s2ToolsEl) {
            s2ToolsEl.innerHTML = sup2Tools.split(",").map(t => `<span class="tool-tag"><i class="fa-solid fa-calculator"></i> ${escHtml(t.trim())}</span>`).join(" ");
        }
    }
}

// ─── PHASE 5: EVIDENCE & PROVENANCE INSPECTOR ────────────────────
async function renderEvidenceInspector(sessionId) {
    if (!sessionId) return;
    try {
        const res = await fetch(`/api/session/${sessionId}/evidence`);
        if (!res.ok) return;
        const data = await res.json();
        window.latestEvidence = data;

        const vEl = document.getElementById("ev-count-verified");
        if (vEl) vEl.textContent = data.verified_count || 0;
        const pEl = document.getElementById("ev-count-partial");
        if (pEl) pEl.textContent = Math.max(0, (data.claims ? data.claims.length : 0) - (data.verified_count || 0) - (data.stale_count || 0));
        const sEl = document.getElementById("ev-count-stale");
        if (sEl) sEl.textContent = data.stale_count || 0;
        const srcEl = document.getElementById("ev-count-sources");
        if (srcEl) srcEl.textContent = data.sources_count || 0;
        const badgeEl = document.getElementById("evidence-badge");
        if (badgeEl) badgeEl.textContent = data.claims ? data.claims.length : 0;

        const list = document.getElementById("evidence-claims-list");
        if (!list) return;

        if (!data.claims || data.claims.length === 0) {
            list.innerHTML = `<div class="report-empty" style="height:180px"><i class="fa-solid fa-circle-info"></i><p>No claims recorded for this inquiry.</p></div>`;
            return;
        }

        list.innerHTML = "";
        data.claims.forEach(c => {
            const statusUpper = (c.status || "").toUpperCase();
            let statusKey = "supported";
            let badgeClass = "claim-badge-verified";
            if (statusUpper.includes("STALE") || statusUpper.includes("HISTORICAL")) {
                statusKey = "stale";
                badgeClass = "claim-badge-stale";
            } else if (statusUpper.includes("PARTIAL") || statusUpper.includes("BOUNDED")) {
                statusKey = "partial";
                badgeClass = "claim-badge-partial";
            } else if (statusUpper.includes("INSUFFICIENT")) {
                statusKey = "insufficient";
                badgeClass = "claim-badge-partial";
            } else if (statusUpper.includes("CONTRADICTED") || statusUpper.includes("REJECTED")) {
                statusKey = "contradicted";
                badgeClass = "claim-badge-stale";
            }

            const chain = c.chain || {};
            const sourceType = c.source_type || chain.source_type || (statusUpper.includes("LOCAL") ? "LOCAL_REFERENCE" : "LIVE_EXTERNAL");
            let sourceBadgeStyle = "background:rgba(99,102,241,0.15);color:#818cf8;";
            if (sourceType.includes("LOCAL")) {
                sourceBadgeStyle = "background:rgba(245,158,11,0.15);color:#fbbf24;";
            } else if (sourceType.includes("CALC")) {
                sourceBadgeStyle = "background:rgba(16,185,129,0.15);color:#34d399;";
            }

            const item = document.createElement("div");
            item.className = "claim-card";
            item.setAttribute("data-status", statusKey);
            item.innerHTML = `
                <div class="claim-card-top">
                    <span class="claim-card-id">${escHtml(c.claim_id)}</span>
                    <span class="claim-card-text">${escHtml(c.claim || c.statement)}</span>
                    <span class="claim-badge" style="font-size:10px;padding:2px 6px;border-radius:4px;font-weight:700;${sourceBadgeStyle}">${escHtml(sourceType.replace(/_/g, ' '))}</span>
                    <span class="claim-badge ${badgeClass}">${escHtml(c.status)}</span>
                </div>
                <div class="claim-meta-row">
                    <span><i class="fa-solid fa-user-shield text-accent"></i> ${escHtml(c.specialist || "Lead")}</span>
                    <span><i class="fa-solid fa-wrench text-indigo"></i> <code>${escHtml(c.tools || "system")}</code></span>
                    <span><i class="fa-solid fa-anchor text-amber"></i> ${escHtml(c.evidence_anchor || "Telemetry")}</span>
                </div>
                <div class="claim-provenance-box">
                    <div class="prov-chain-title"><i class="fa-solid fa-link"></i> Provenance Lineage Chain</div>
                    <div class="prov-field"><strong>Source Anchor:</strong> ${escHtml(chain.source_anchor || "Empirical Benchmark")}</div>
                    <div class="prov-field"><strong>Extracted Fact:</strong> "${escHtml(chain.extracted_fact || c.claim || c.statement)}"</div>
                    <div class="prov-field"><strong>Originating Node:</strong> <code>${escHtml(chain.originating_node || "task_lead")}</code> | <strong>Attributed Specialist:</strong> ${escHtml(chain.attributed_specialist || c.specialist)}</div>
                    <div class="prov-field"><strong>Tool Executed:</strong> <code>${escHtml(chain.tools_executed || c.tools)}</code></div>
                    <div class="prov-field"><strong>Critic Verdict:</strong> <span style="color:#10b981;font-weight:700;">${escHtml(chain.critic_verdict || "SUPPORTED (GREEN)")}</span></div>
                </div>
            `;
            list.appendChild(item);
        });
    } catch(e) {
        console.error("renderEvidenceInspector error:", e);
    }
}

function filterEvidence(filterType) {
    document.querySelectorAll(".ev-filter-btn").forEach(btn => btn.classList.remove("active"));
    const activeBtn = document.getElementById(`ev-filt-${filterType}`);
    if (activeBtn) activeBtn.classList.add("active");

    document.querySelectorAll(".claim-card").forEach(card => {
        const st = card.getAttribute("data-status");
        if (filterType === "all" || st === filterType) {
            card.style.display = "block";
        } else {
            card.style.display = "none";
        }
    });
}

// ─── PHASE 5: EXPORT TOOLBAR HANDLERS ─────────────────────────────
async function exportEvidenceJSON() {
    if (!activeSessionId) { alert("No active session to export."); return; }
    try {
        const res = await fetch(`/api/session/${activeSessionId}/evidence`);
        const data = await res.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `neuroweave_evidence_${activeSessionId.slice(0,8)}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    } catch(e) { alert("Export Evidence failed: " + e); }
}

async function exportFlowJSON() {
    if (!activeSessionId) { alert("No active session to export."); return; }
    try {
        const res = await fetch(`/api/session/${activeSessionId}/export-flow`);
        const data = await res.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `neuroweave_flow_v2_${activeSessionId.slice(0,8)}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    } catch(e) { alert("Export Flow failed: " + e); }
}

async function exportSessionJSON() {
    if (!activeSessionId) { alert("No active session to export."); return; }
    try {
        const res = await fetch(`/api/session/${activeSessionId}/export-session`);
        const data = await res.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `neuroweave_session_${activeSessionId.slice(0,8)}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    } catch(e) { alert("Export Session failed: " + e); }
}

// ─── PHASE 5: REAL TELEMETRY COMPUTATION ──────────────────────────
function updateTelemetryStats(state) {
    const traces = state.traces || [];
    let totalSec = 0.0;
    traces.forEach(t => { totalSec += (t.duration_sec || 0); });

    const timeEl = document.getElementById("tel-val-total-time");
    if (timeEl) timeEl.textContent = `${totalSec.toFixed(2)}s`;

    const tasksCount = Object.keys(state.tasks || {}).length;
    const tasksEl = document.getElementById("tel-val-tasks-count");
    if (tasksEl) tasksEl.textContent = tasksCount;

    let sandboxCount = 0;
    Object.values(state.tasks || {}).forEach(t => {
        const ag = (t.assigned_agent || "").toLowerCase();
        const tit = (t.title || "").toLowerCase();
        if (ag === "analyzer" || tit.includes("analyzer") || tit.includes("sandbox")) {
            sandboxCount++;
        }
    });
    const sCountEl = document.getElementById("tel-val-sandbox-count");
    if (sCountEl) sCountEl.textContent = sandboxCount;

    const replans = (state.metrics && state.metrics.replanning_cycle_count) || 0;
    const repEl = document.getElementById("tel-val-replans-count");
    if (repEl) repEl.textContent = replans;
}

function agentLabel(agent) {
    const map = {
        intent_analyzer: "Intent & Persona Mapping...",
        planner:         "Formulating Task DAG...",
        researcher:      "Deep Web Intelligence...",
        analyzer:        "Quantitative Sandbox Math...",
        critic:          "NEXUS Quality Audit...",

        debate_engine:   "Dialectical Debate...",
        synthesizer:     "Executive Synthesis..."
    };
    return map[agent] || "Processing Research...";
}

// ─── RENDER LOGS ─────────────────────────────────────────────────
function renderLogs(logs) {
    const stream = document.getElementById("terminal-thought-stream");
    const prevCount = logCount;
    
    if (logs.length > logCount) {
        for (let i = logCount; i < logs.length; i++) {
            const log = logs[i];
            appendLog(log.type, log.agent, log.message, log.timestamp);
        }
        logCount = logs.length;
        const countBadge = document.getElementById("log-count-badge");
        if (countBadge) countBadge.textContent = logCount;

        const notif = document.getElementById("logs-notif");
        if (!logsOpen && logCount > prevCount && notif) {
            notif.style.display = "block";
        }
    }
}

function appendLog(type, agent, message, timestamp) {
    const stream = document.getElementById("terminal-thought-stream");
    if (!stream) return;
    const row = document.createElement("div");
    row.className = `log-entry log-${(agent || type || "system").toLowerCase()}`;

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

// ─── ACTIVE SKILLS & PERSONA CHIPS ───────────────────────────────
function formatSkill(skill) {
    if (!skill) return null;
    let name = "";
    let icon = "";

    if (typeof skill === "string") {
        name = skill.trim();
    } else if (typeof skill === "object") {
        name = (skill.name || skill.title || skill.id || "").trim();
        icon = (skill.icon || skill.emoji || "").trim();
    }

    if (!name) return null;

    const key = name.toLowerCase().replace(/[\s_-]+/g, "_");
    const defaultSkillMap = {
        market_analysis:        { icon: "🎯", label: "Market Sizing & TAM" },
        financial_valuation:    { icon: "💰", label: "DCF & Cap Table" },
        tech_architecture:      { icon: "🏗️", label: "System Architecture" },
        fact_checking:          { icon: "🔍", label: "Fact Verification" },
        data_visualization:     { icon: "📊", label: "Data Visualization" },
        customer_research:      { icon: "👥", label: "Customer Profiling" },
        competitor_analysis:    { icon: "⚔️", label: "Competitor Benchmarking" },
        launch_strategy:        { icon: "🚀", label: "Launch Strategy" },
        api_security:           { icon: "🛡️", label: "API Security Audit" },
        ml_autoresearch:        { icon: "🧠", label: "AutoResearch & ML Loop" },
        transformer_mechanics:  { icon: "⚡", label: "Transformer & nanoGPT Mechanics" }
    };

    const match = defaultSkillMap[key];
    if (match) {
        if (!icon) icon = match.icon;
        name = match.label;
    } else {
        if (!icon) icon = "✨";
        name = name.split("_").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
    }

    return { text: name, icon: icon };
}

function renderActiveSkills(skills, persona, personaMeta) {
    const bar = document.getElementById("active-skills-bar");
    const list = document.getElementById("active-skills-list");
    if (!bar || !list) return;

    list.innerHTML = "";
    let hasContent = false;

    // Render Specialist Persona Chip from 261 Agency Agents
    if (persona || (personaMeta && personaMeta.name)) {
        hasContent = true;
        const pName = (personaMeta && personaMeta.name) || persona;
        const pRole = (personaMeta && personaMeta.role) || "Specialist";
        const pDiv  = (personaMeta && personaMeta.division) || "General";
        const pEmoji = (personaMeta && personaMeta.emoji) || "🤖";
        const pColor = (personaMeta && personaMeta.color) || "#6366F1";
        const pVibe = (personaMeta && personaMeta.vibe) || "";

        const personaChip = document.createElement("div");
        personaChip.className = "skill-chip persona-chip-active";
        personaChip.style.borderColor = pColor;
        personaChip.innerHTML = `<span class="skill-icon">${pEmoji}</span><span class="skill-name">${escHtml(pName)} <small style="opacity:0.75;font-weight:400">(${escHtml(pDiv)})</small></span>`;
        personaChip.title = `${pName} — ${pRole} [${pDiv}]${pVibe ? '\n"' + pVibe + '"' : ''}`;
        list.appendChild(personaChip);

        // Update telemetry statusbar
        const telPersona = document.getElementById("tel-persona");
        if (telPersona) {
            telPersona.textContent = `${pEmoji} ${pName}`;
            telPersona.title = `${pRole} [${pDiv}]`;
        }
    }

    // Render Domain Capabilities
    if (skills && Array.isArray(skills) && skills.length > 0) {
        const validSkills = skills.map(formatSkill).filter(Boolean);
        if (validSkills.length > 0) {
            hasContent = true;
            validSkills.forEach((item) => {
                const chip = document.createElement("div");
                chip.className = "skill-chip";
                chip.innerHTML = `<span class="skill-icon">${item.icon}</span><span class="skill-name">${escHtml(item.text)}</span>`;
                list.appendChild(chip);
            });
        }
    }

    bar.style.display = hasContent ? "flex" : "none";
}

// ─── RENDER REPORT & MARKDOWN ────────────────────────────────────
function renderReport(md) {
    const box = document.getElementById("report-output-box");
    if (!box) return;
    if (!md) { box.innerHTML = ""; return; }
    
    // Destroy previous Chart.js instances to prevent canvas reuse errors and memory leaks
    if (window.activeChartInstances && Array.isArray(window.activeChartInstances)) {
        window.activeChartInstances.forEach(chart => {
            try {
                if (chart && typeof chart.destroy === "function") {
                    chart.destroy();
                }
            } catch(err) {
                console.debug("[Chart.js] Destroy error:", err);
            }
        });
    }
    window.activeChartInstances = [];
    window.chartQueue = [];

    box.innerHTML = parseMarkdown(md);
    
    // Process chart queue with responsive dark-theme options
    if (window.chartQueue && window.chartQueue.length > 0) {
        window.chartQueue.forEach(item => {
            const canvasEl = document.getElementById(item.id);
            if (!canvasEl) return;
            try {
                let parsedConfig;
                if (typeof item.config === "string") {
                    try {
                        parsedConfig = JSON.parse(item.config);
                    } catch (jsonErr) {
                        // Relaxed JSON parsing for LLM output (relaxed quotes/trailing commas)
                        const sanitized = item.config
                            .replace(/([{,]\s*)([a-zA-Z0-9_]+)\s*:/g, '$1"$2":')
                            .replace(/'/g, '"')
                            .replace(/,\s*([}\]])/g, '$1');
                        parsedConfig = JSON.parse(sanitized);
                    }
                } else {
                    parsedConfig = item.config;
                }

                parsedConfig.options = parsedConfig.options || {};
                parsedConfig.options.responsive = true;
                parsedConfig.options.maintainAspectRatio = false;
                
                // Typography presets
                const defaultFont = { family: "'Plus Jakarta Sans', sans-serif", size: 11, weight: '500' };
                const monoFont = { family: "'JetBrains Mono', monospace", size: 11 };

                // Vibrant high-contrast color palettes
                const modernColors = [
                    '#6366f1', '#10b981', '#f59e0b', '#06b6d4', '#8b5cf6', '#ec4899', '#3b82f6', '#14b8a6', '#f43f5e'
                ];
                const modernFills = [
                    'rgba(99, 102, 241, 0.35)', 'rgba(16, 185, 129, 0.35)', 'rgba(245, 158, 11, 0.35)',
                    'rgba(6, 182, 212, 0.35)', 'rgba(139, 92, 246, 0.35)', 'rgba(236, 72, 153, 0.35)',
                    'rgba(59, 130, 246, 0.35)', 'rgba(20, 184, 166, 0.35)', 'rgba(244, 63, 94, 0.35)'
                ];

                if (parsedConfig.data && Array.isArray(parsedConfig.data.datasets)) {
                    parsedConfig.data.datasets.forEach((ds, idx) => {
                        const isCircular = ['pie', 'doughnut', 'polarArea'].includes(parsedConfig.type);
                        if (!ds.backgroundColor) {
                            ds.backgroundColor = isCircular ? modernFills : modernFills[idx % modernFills.length];
                        }
                        if (!ds.borderColor) {
                            ds.borderColor = isCircular ? modernColors : modernColors[idx % modernColors.length];
                        }
                        if (ds.borderWidth === undefined) ds.borderWidth = 2;
                        if (parsedConfig.type === 'line' && ds.tension === undefined) ds.tension = 0.35;
                    });
                }

                // Global chart options plugin styling
                parsedConfig.options.plugins = parsedConfig.options.plugins || {};
                
                // Legend styling
                parsedConfig.options.plugins.legend = parsedConfig.options.plugins.legend || {};
                parsedConfig.options.plugins.legend.labels = parsedConfig.options.plugins.legend.labels || {};
                parsedConfig.options.plugins.legend.labels.color = '#cbd5e1';
                parsedConfig.options.plugins.legend.labels.font = defaultFont;
                parsedConfig.options.plugins.legend.labels.padding = 14;

                // Tooltip styling
                parsedConfig.options.plugins.tooltip = parsedConfig.options.plugins.tooltip || {};
                parsedConfig.options.plugins.tooltip.backgroundColor = 'rgba(10, 14, 26, 0.95)';
                parsedConfig.options.plugins.tooltip.titleColor = '#ffffff';
                parsedConfig.options.plugins.tooltip.bodyColor = '#cbd5e1';
                parsedConfig.options.plugins.tooltip.borderColor = 'rgba(99, 102, 241, 0.4)';
                parsedConfig.options.plugins.tooltip.borderWidth = 1;
                parsedConfig.options.plugins.tooltip.padding = 10;
                parsedConfig.options.plugins.tooltip.cornerRadius = 8;
                parsedConfig.options.plugins.tooltip.titleFont = { family: "'Plus Jakarta Sans', sans-serif", weight: '700', size: 12 };
                parsedConfig.options.plugins.tooltip.bodyFont = monoFont;

                // Scales styling for axis-based charts
                if (['bar', 'line', 'scatter', 'bubble'].includes(parsedConfig.type)) {
                    parsedConfig.options.scales = parsedConfig.options.scales || {};
                    ['x', 'y'].forEach(axis => {
                        parsedConfig.options.scales[axis] = parsedConfig.options.scales[axis] || {};
                        parsedConfig.options.scales[axis].grid = parsedConfig.options.scales[axis].grid || {};
                        parsedConfig.options.scales[axis].grid.color = 'rgba(255, 255, 255, 0.06)';
                        parsedConfig.options.scales[axis].grid.borderColor = 'rgba(255, 255, 255, 0.12)';
                        parsedConfig.options.scales[axis].ticks = parsedConfig.options.scales[axis].ticks || {};
                        parsedConfig.options.scales[axis].ticks.color = '#94a3b8';
                        parsedConfig.options.scales[axis].ticks.font = monoFont;
                    });
                }

                const chartInstance = new Chart(canvasEl, parsedConfig);
                window.activeChartInstances.push(chartInstance);
            } catch(e) {
                console.error("[Chart.js] Initialization error:", e);
                const wrapper = canvasEl.parentElement;
                if (wrapper) {
                    wrapper.innerHTML = `<div class="chart-error"><i class="fa-solid fa-triangle-exclamation text-amber"></i> <span>Visualization could not be initialized: ${escHtml(e.message)}</span></div>`;
                }
            }
        });
        window.chartQueue = [];
    }
}

function parseMarkdown(md) {
    if (!md) return "";
    const lines  = md.split(/\r?\n/);
    const blocks = [];
    
    let inTable = false, tableRows = [];
    let inList = false, listItems = [], listType = "ul";
    let inCode = false, codeBuf = [], codeType = "";
    let inCallout = false, calloutType = "", calloutLines = [];
    let bibItems = [];

    function flushTable() {
        if (!tableRows.length) return;
        let h = '<div class="table-responsive"><table>';
        const isDivider = (r) => r.every(c => /^[-:\s]+$/.test(c));
        if (tableRows.length > 1 && isDivider(tableRows[1])) {
            h += '<thead><tr>' + tableRows[0].map(c => `<th>${inlineMarkdown(c)}</th>`).join('') + '</tr></thead>';
            h += '<tbody>' + tableRows.slice(2).map(r =>
                '<tr>' + r.map(c => `<td>${inlineMarkdown(c)}</td>`).join('') + '</tr>').join('') + '</tbody>';
        } else {
            h += '<tbody>' + tableRows.map(r =>
                '<tr>' + r.map(c => `<td>${inlineMarkdown(c)}</td>`).join('') + '</tr>').join('') + '</tbody>';
        }
        h += '</table></div>';
        blocks.push(h);
        tableRows = [];
        inTable = false;
    }

    function flushList() {
        if (!listItems.length) return;
        const tag = listType === "ol" ? "ol" : "ul";
        blocks.push(`<${tag}>` + listItems.map(i => `<li>${inlineMarkdown(i)}</li>`).join('') + `</${tag}>`);
        listItems = [];
        inList = false;
        listType = "ul";
    }

    function flushCode() {
        if (!codeBuf.length && !codeType) return;
        const rawCode = codeBuf.join('\n');
        const trimmedType = (codeType || "").toLowerCase().trim();
        const isChart = /^(?:json[\s:]+chart|chart[\s:]*json|chart|chartjs)$/i.test(trimmedType);

        if (isChart) {
            const chartId = "chart-" + Math.random().toString(36).substr(2, 9);
            blocks.push(`
                <div class="chart-card glass-panel">
                    <div class="chart-card-header">
                        <div class="chart-header-title">
                            <i class="fa-solid fa-chart-simple text-accent"></i>
                            <span>Interactive Data Visualization</span>
                        </div>
                        <span class="chart-type-badge"><i class="fa-solid fa-chart-pie"></i> Chart.js</span>
                    </div>
                    <div class="chart-canvas-wrapper">
                        <canvas id="${chartId}"></canvas>
                    </div>
                </div>
            `);
            window.chartQueue = window.chartQueue || [];
            window.chartQueue.push({ id: chartId, config: rawCode });
        } else {
            const codeBlockId = "code-" + Math.random().toString(36).substr(2, 9);
            const langLabel = trimmedType || "text";
            blocks.push(`
                <div class="code-block-wrapper">
                    <div class="code-block-header">
                        <span class="code-lang-tag">${escHtml(langLabel)}</span>
                        <button class="code-copy-btn" onclick="copyCodeBlock('${codeBlockId}')" title="Copy code">
                            <i class="fa-solid fa-copy"></i> <span>Copy</span>
                        </button>
                    </div>
                    <pre><code id="${codeBlockId}" class="language-${escHtml(langLabel)}">${escHtml(rawCode)}</code></pre>
                </div>
            `);
        }
        codeBuf = [];
        inCode = false;
        codeType = "";
    }

    function flushCallout() {
        if (!inCallout) return;
        const type = calloutType || "note";
        const iconMap = {
            note: 'fa-solid fa-circle-info',
            tip: 'fa-solid fa-lightbulb',
            important: 'fa-solid fa-circle-exclamation',
            warning: 'fa-solid fa-triangle-exclamation',
            caution: 'fa-solid fa-shield-halved'
        };
        const titleMap = {
            note: 'NOTE',
            tip: 'TIP',
            important: 'IMPORTANT',
            warning: 'WARNING',
            caution: 'CAUTION'
        };
        const icon = iconMap[type] || 'fa-solid fa-circle-info';
        const label = titleMap[type] || type.toUpperCase();
        const contentHtml = calloutLines.map(line => `<p>${inlineMarkdown(line)}</p>`).join('');

        blocks.push(`
            <div class="report-callout callout-${type}">
                <div class="callout-header">
                    <i class="${icon}"></i>
                    <span class="callout-badge">${label}</span>
                </div>
                <div class="callout-content">
                    ${contentHtml}
                </div>
            </div>
        `);
        inCallout = false;
        calloutType = "";
        calloutLines = [];
    }

    for (const line of lines) {
        const t = line.trim();

        // Code fence
        if (t.startsWith("```")) {
            if (inCode) {
                flushCode();
            } else {
                if (inTable) flushTable();
                if (inList) flushList();
                if (inCallout) flushCallout();
                inCode = true;
                codeType = t.slice(3).trim();
            }
            continue;
        }
        if (inCode) {
            codeBuf.push(line);
            continue;
        }

        // Bibliography definition item e.g. [^1]: https://... or [^1]: [Title](url)
        const bibMatch = t.match(/^\[\^(\d+)\]:\s*(.*)/);
        if (bibMatch) {
            if (inTable) flushTable();
            if (inList) flushList();
            if (inCallout) flushCallout();
            bibItems.push({ num: bibMatch[1], content: bibMatch[2] });
            continue;
        }

        // Alert Callouts: > [!NOTE], > [!TIP], > [!IMPORTANT], > [!WARNING], > [!CAUTION]
        const alertHeaderMatch = t.match(/^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*(.*)/i);
        if (alertHeaderMatch) {
            if (inTable) flushTable();
            if (inList) flushList();
            if (inCallout) flushCallout();
            inCallout = true;
            calloutType = alertHeaderMatch[1].toLowerCase();
            calloutLines = [];
            if (alertHeaderMatch[2].trim()) {
                calloutLines.push(alertHeaderMatch[2].trim());
            }
            continue;
        }

        // Continuous blockquote line
        if (t.startsWith(">")) {
            if (inTable) flushTable();
            if (inList) flushList();
            const quoteText = t.replace(/^>\s*/, "").trim();
            if (!inCallout) {
                inCallout = true;
                calloutType = "important"; // Default callout style
                calloutLines = [];
            }
            if (quoteText) {
                calloutLines.push(quoteText);
            }
            continue;
        } else if (inCallout) {
            flushCallout();
        }

        // Horizontal Rule
        if (/^---+$/.test(t) || /^\*\*\*+$/.test(t) || /^___+$/.test(t)) {
            if (inTable) flushTable();
            if (inList) flushList();
            blocks.push('<hr>');
            continue;
        }

        // Table row
        if (t.startsWith("|") && t.endsWith("|")) {
            if (inList) flushList();
            inTable = true;
            tableRows.push(t.slice(1, -1).split("|").map(c => c.trim()));
            continue;
        } else if (inTable) {
            flushTable();
        }

        // Unordered List item
        if (/^[-*+]\s+/.test(t)) {
            if (inTable) flushTable();
            if (!inList || listType !== "ul") {
                if (inList) flushList();
                inList = true;
                listType = "ul";
            }
            listItems.push(t.replace(/^[-*+]\s+/, ""));
            continue;
        }

        // Ordered List item
        if (/^\d+\.\s+/.test(t)) {
            if (inTable) flushTable();
            if (!inList || listType !== "ol") {
                if (inList) flushList();
                inList = true;
                listType = "ol";
            }
            listItems.push(t.replace(/^\d+\.\s+/, ""));
            continue;
        }

        if (inList) {
            flushList();
        }

        // Blank line
        if (!t) {
            continue;
        }

        // Headings
        if (t.startsWith("# ")) {
            blocks.push(`<h1>${inlineMarkdown(t.slice(2))}</h1>`);
            continue;
        } else if (t.startsWith("## ")) {
            blocks.push(`<h2>${inlineMarkdown(t.slice(3))}</h2>`);
            continue;
        } else if (t.startsWith("### ")) {
            blocks.push(`<h3>${inlineMarkdown(t.slice(4))}</h3>`);
            continue;
        } else if (t.startsWith("#### ")) {
            blocks.push(`<h4>${inlineMarkdown(t.slice(5))}</h4>`);
            continue;
        }

        // Standard Paragraph
        blocks.push(`<p>${inlineMarkdown(t)}</p>`);
    }

    if (inTable) flushTable();
    if (inList) flushList();
    if (inCallout) flushCallout();
    if (inCode) flushCode();

    // Append Bibliography if collected
    if (bibItems.length > 0) {
        let bibHtml = `
            <div class="report-bibliography glass-panel">
                <div class="bib-header">
                    <i class="fa-solid fa-book-bookmark text-accent"></i>
                    <span>Sources &amp; Citations</span>
                </div>
                <ol class="bib-list">
        `;
        bibItems.forEach(b => {
            bibHtml += `
                <li id="bib-${b.num}" class="bib-item">
                    <span class="bib-num">[${b.num}]</span>
                    <span class="bib-content">${inlineMarkdown(b.content)}</span>
                </li>
            `;
        });
        bibHtml += `</ol></div>`;
        blocks.push(bibHtml);
    }

    return blocks.join("\n");
}

function inlineMarkdown(text) {
    if (!text) return "";
    return text
        .replace(/\*\*\*(.*?)\*\*\*/g,       '<strong><em>$1</em></strong>')
        .replace(/\*\*(.*?)\*\*/g,           '<strong>$1</strong>')
        .replace(/__([^_]+)__/g,             '<strong>$1</strong>')
        .replace(/\*([^*]+)\*/g,             '<em>$1</em>')
        .replace(/_([^_]+)_/g,               '<em>$1</em>')
        .replace(/~~(.*?)~~/g,               '<del>$1</del>')
        .replace(/`([^`]+)`/g,               '<code>$1</code>')
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1 <i class="fa-solid fa-arrow-up-right-from-square inline-link-icon"></i></a>')
        .replace(/\[\^(\d+)\](?!:)/g,        '<sup><a href="#bib-$1" class="citation-ref" title="Reference [$1]">[$1]</a></sup>');
}

function copyCodeBlock(id) {
    const codeEl = document.getElementById(id);
    if (!codeEl) return;
    navigator.clipboard.writeText(codeEl.textContent).then(() => {
        const btn = codeEl.closest(".code-block-wrapper")?.querySelector(".code-copy-btn");
        if (btn) {
            btn.innerHTML = `<i class="fa-solid fa-check"></i> <span>Copied!</span>`;
            btn.style.color = "#10b981";
            setTimeout(() => {
                btn.innerHTML = `<i class="fa-solid fa-copy"></i> <span>Copy</span>`;
                btn.style.color = "";
            }, 2000);
        }
    });
}

// ─── OPAL VISUAL EXECUTION GRAPH (DAG) ───────────────────────────
function plotGraph(tasks, activeAgent) {
    window.latestTasks = tasks;
    window.latestActiveAgent = activeAgent;

    const svg = document.getElementById("svg-graph");
    if (!svg) return;
    svg.innerHTML = "";

    const taskList = Object.values(tasks || {});
    if (taskList.length === 0) {
        svg.innerHTML = `
            <text x="50%" y="50%" text-anchor="middle" fill="rgba(255,255,255,0.25)"
                font-size="14" font-family="'Plus Jakarta Sans', sans-serif">
                No active tasks in DAG queue. Run an analysis to visualize the execution graph.
            </text>`;
        return;
    }

    const emojiMap = { 
        researcher: "🔍", 
        analyzer: "📊", 
        critic: "🛡️", 
        planner: "🗺️", 
        intent_analyzer: "🤖", 
        synthesizer: "📑" 
    };

    const roleMap = {
        researcher: "WEB INTELLIGENCE",
        analyzer: "DATA & SANDBOX MATH",
        critic: "SECURITY AUDITOR",
        planner: "DAG ARCHITECT",
        intent_analyzer: "INTENT CLASSIFIER",
        synthesizer: "STRATEGIC COMPILER"
    };

    // Layer by dependency depth
    const layers = {};
    taskList.forEach(t => {
        const depth = (function d(id) {
            const node = tasks[id];
            if (!node || !node.dependencies || !node.dependencies.length) return 0;
            return 1 + Math.max(...node.dependencies.map(d));
        })(t.id);
        (layers[depth] = layers[depth] || []).push(t);
    });

    const depthKeys = Object.keys(layers).sort((a,b) => a-b);
    const CARD_W = 230;
    const CARD_H = 82;
    const CARD_R = 12;

    const maxColNodes = Math.max(...Object.values(layers).map(col => col.length), 1);
    const totalCols   = Math.max(depthKeys.length, 1);

    const W = Math.max(960, totalCols * 290 + 60);
    const H = Math.max(460, maxColNodes * 130 + 80);

    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("width", "100%");
    svg.setAttribute("height", "100%");

    const colStep = totalCols > 1 ? (W - 80 - CARD_W) / (totalCols - 1) : 0;
    const coords = {};

    depthKeys.forEach((k, colIndex) => {
        const col = layers[k];
        const x = totalCols === 1 ? (W - CARD_W)/2 : 40 + colIndex * colStep;
        const rowStep = H / (col.length + 1);
        col.forEach((t, rowIndex) => {
            const y = rowStep * (rowIndex + 1) - (CARD_H / 2);
            coords[t.id] = { x, y, cx: x + CARD_W/2, cy: y + CARD_H/2 };
        });
    });

    // SVG Defs: Filters, Markers & Dot Grid Matrix
    const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    defs.innerHTML = `
        <pattern id="opal-grid" width="24" height="24" patternUnits="userSpaceOnUse">
            <circle cx="12" cy="12" r="1.1" fill="rgba(255,255,255,0.06)"/>
        </pattern>
        <filter id="glow-running" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="0" stdDeviation="6" flood-color="#818cf8" flood-opacity="0.65"/>
        </filter>
        <filter id="glow-done" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="0" stdDeviation="4" flood-color="#10b981" flood-opacity="0.35"/>
        </filter>
        <filter id="card-shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="6" stdDeviation="10" flood-color="#000000" flood-opacity="0.6"/>
        </filter>
        <linearGradient id="grad-card-bg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#101524" />
            <stop offset="100%" stop-color="#161c30" />
        </linearGradient>
        <linearGradient id="grad-running-bg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#161b36" />
            <stop offset="100%" stop-color="#1e2246" />
        </linearGradient>
        <linearGradient id="grad-completed-bg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#0e1b24" />
            <stop offset="100%" stop-color="#12252a" />
        </linearGradient>
        <marker id="opal-arrow" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#6366f1" />
        </marker>
        <marker id="opal-arrow-done" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#10b981" />
        </marker>
        <marker id="opal-arrow-fail" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#ef4444" />
        </marker>
    `;
    svg.appendChild(defs);

    // Canvas Background Dot Grid Matrix
    const bgRect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    bgRect.setAttribute("width", "100%");
    bgRect.setAttribute("height", "100%");
    bgRect.setAttribute("fill", "url(#opal-grid)");
    svg.appendChild(bgRect);

    // Render Flowing Bezier Connecting Lines
    taskList.forEach(t => {
        const tgt = coords[t.id];
        (t.dependencies || []).forEach(dep => {
            const src = coords[dep];
            if (!src || !tgt) return;

            const startX = src.x + CARD_W;
            const startY = src.y + CARD_H / 2;
            const endX   = tgt.x;
            const endY   = tgt.y + CARD_H / 2;
            const midX   = (startX + endX) / 2;

            const d = `M ${startX} ${startY} C ${midX} ${startY}, ${midX} ${endY}, ${endX - 4} ${endY}`;
            const isCompleted = t.status === "completed";
            const isRunning   = t.status === "running";
            const isFailed    = t.status === "failed";

            const trackColor = isFailed ? "#ef4444" : (isCompleted ? "#10b981" : (isRunning ? "#818cf8" : "rgba(99, 102, 241, 0.25)"));
            const marker = isFailed ? "url(#opal-arrow-fail)" : (isCompleted ? "url(#opal-arrow-done)" : "url(#opal-arrow)");

            // Base Track
            const baseTrack = document.createElementNS("http://www.w3.org/2000/svg", "path");
            baseTrack.setAttribute("d", d);
            baseTrack.setAttribute("fill", "none");
            baseTrack.setAttribute("stroke", trackColor);
            baseTrack.setAttribute("stroke-width", "2.5");
            baseTrack.setAttribute("marker-end", marker);
            baseTrack.setAttribute("opacity", isCompleted ? "0.9" : (isRunning ? "0.85" : "0.45"));
            svg.appendChild(baseTrack);

            // Flowing Particle Energy Pulse Line (when active or done)
            if (isRunning || isCompleted) {
                const pulseLine = document.createElementNS("http://www.w3.org/2000/svg", "path");
                pulseLine.setAttribute("d", d);
                pulseLine.setAttribute("fill", "none");
                pulseLine.setAttribute("stroke", isCompleted ? "#34d399" : "#a5b4fc");
                pulseLine.setAttribute("stroke-width", "2.5");
                pulseLine.setAttribute("stroke-dasharray", "8 6");
                pulseLine.classList.add("opal-cable-flow");
                pulseLine.setAttribute("opacity", "0.8");
                svg.appendChild(pulseLine);
            }
        });
    });

    // Render Opal Glassmorphic Node Cards
    taskList.forEach((t, idx) => {
        const c = coords[t.id];
        if (!c) return;

        const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
        g.classList.add("opal-node-group");
        g.setAttribute("style", "cursor: pointer; pointer-events: all;");
        g.setAttribute("data-task-id", t.id);
        g.onclick = (e) => { e.stopPropagation(); openNodeInspector(t.id); };
        g.addEventListener("click", (e) => { e.stopPropagation(); openNodeInspector(t.id); });

        const isRunning   = t.status === "running";
        const isCompleted = t.status === "completed";
        const isFailed    = t.status === "failed";

        let borderColor = "rgba(255, 255, 255, 0.12)";
        let bgGradient  = "url(#grad-card-bg)";
        let filterAttr  = "url(#card-shadow)";
        let badgeColor  = "#94a3b8";
        let badgeBg     = "rgba(255, 255, 255, 0.06)";
        let badgeText   = "QUEUED";

        if (isRunning) {
            borderColor = "#818cf8";
            bgGradient  = "url(#grad-running-bg)";
            filterAttr  = "url(#glow-running)";
            badgeColor  = "#a5b4fc";
            badgeBg     = "rgba(99, 102, 241, 0.25)";
            badgeText   = "⚡ RUNNING";
        } else if (isCompleted) {
            borderColor = "#10b981";
            bgGradient  = "url(#grad-completed-bg)";
            filterAttr  = "url(#glow-done)";
            badgeColor  = "#6ee7b7";
            badgeBg     = "rgba(16, 185, 129, 0.2)";
            badgeText   = "✓ DONE";
        } else if (isFailed) {
            borderColor = "#ef4444";
            badgeColor  = "#fca5a5";
            badgeBg     = "rgba(239, 68, 68, 0.2)";
            badgeText   = "FAILED";
        }

        // 1. Card Container
        const cardRect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        cardRect.setAttribute("x", c.x);
        cardRect.setAttribute("y", c.y);
        cardRect.setAttribute("width", CARD_W);
        cardRect.setAttribute("height", CARD_H);
        cardRect.setAttribute("rx", CARD_R);
        cardRect.setAttribute("fill", bgGradient);
        cardRect.setAttribute("stroke", borderColor);
        cardRect.setAttribute("stroke-width", isRunning ? "2" : "1.5");
        cardRect.setAttribute("filter", filterAttr);
        g.appendChild(cardRect);

        // 2. Avatar Circle Icon
        const iconCircle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        iconCircle.setAttribute("cx", c.x + 22);
        iconCircle.setAttribute("cy", c.y + 24);
        iconCircle.setAttribute("r", 13);
        iconCircle.setAttribute("fill", isCompleted ? "rgba(16, 185, 129, 0.2)" : (isRunning ? "rgba(99, 102, 241, 0.25)" : "rgba(255,255,255,0.06)"));
        iconCircle.setAttribute("stroke", borderColor);
        iconCircle.setAttribute("stroke-width", "1");
        g.appendChild(iconCircle);

        const iconText = document.createElementNS("http://www.w3.org/2000/svg", "text");
        iconText.setAttribute("x", c.x + 22);
        iconText.setAttribute("y", c.y + 28);
        iconText.setAttribute("text-anchor", "middle");
        iconText.setAttribute("font-size", "13");
        iconText.textContent = emojiMap[t.assigned_agent] || "⚙️";
        g.appendChild(iconText);

        // 3. Agent Role Tag
        const roleText = document.createElementNS("http://www.w3.org/2000/svg", "text");
        roleText.setAttribute("x", c.x + 42);
        roleText.setAttribute("y", c.y + 21);
        roleText.setAttribute("font-family", "Inter, sans-serif");
        roleText.setAttribute("font-size", "9");
        roleText.setAttribute("font-weight", "700");
        roleText.setAttribute("letter-spacing", "0.6px");
        roleText.setAttribute("fill", isRunning ? "#c4b5fd" : (isCompleted ? "#6ee7b7" : "#94a3b8"));
        roleText.textContent = roleMap[t.assigned_agent] || (t.assigned_agent || "AGENT").toUpperCase();
        g.appendChild(roleText);

        // 4. Status Badge Pill
        const pillW = 68, pillH = 18;
        const pillX = c.x + CARD_W - pillW - 10;
        const pillY = c.y + 13;

        const pillRect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        pillRect.setAttribute("x", pillX);
        pillRect.setAttribute("y", pillY);
        pillRect.setAttribute("width", pillW);
        pillRect.setAttribute("height", pillH);
        pillRect.setAttribute("rx", "9");
        pillRect.setAttribute("fill", badgeBg);
        pillRect.setAttribute("stroke", borderColor);
        pillRect.setAttribute("stroke-width", "0.8");
        g.appendChild(pillRect);

        const pillTxt = document.createElementNS("http://www.w3.org/2000/svg", "text");
        pillTxt.setAttribute("x", pillX + pillW/2);
        pillTxt.setAttribute("y", pillY + 12);
        pillTxt.setAttribute("text-anchor", "middle");
        pillTxt.setAttribute("font-family", "Inter, sans-serif");
        pillTxt.setAttribute("font-size", "8.5");
        pillTxt.setAttribute("font-weight", "700");
        pillTxt.setAttribute("fill", badgeColor);
        pillTxt.textContent = badgeText;
        g.appendChild(pillTxt);

        // 5. Divider Line inside card
        const cardLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
        cardLine.setAttribute("x1", c.x + 10);
        cardLine.setAttribute("y1", c.y + 39);
        cardLine.setAttribute("x2", c.x + CARD_W - 10);
        cardLine.setAttribute("y2", c.y + 39);
        cardLine.setAttribute("stroke", "rgba(255,255,255,0.06)");
        cardLine.setAttribute("stroke-width", "1");
        g.appendChild(cardLine);

        // 6. Task Title (Clean bold font)
        const titleText = document.createElementNS("http://www.w3.org/2000/svg", "text");
        titleText.setAttribute("x", c.x + 12);
        titleText.setAttribute("y", c.y + 55);
        titleText.setAttribute("font-family", "Inter, sans-serif");
        titleText.setAttribute("font-size", "11");
        titleText.setAttribute("font-weight", "600");
        titleText.setAttribute("fill", isCompleted ? "#f1f5f9" : (isRunning ? "#ffffff" : "#cbd5e1"));
        
        let displayTitle = t.title || `Task #${idx+1}`;
        if (displayTitle.length > 28) {
            displayTitle = displayTitle.slice(0, 26) + "...";
        }
        titleText.textContent = displayTitle;
        g.appendChild(titleText);

        // 7. Subtitle / Step Indicator
        const subText = document.createElementNS("http://www.w3.org/2000/svg", "text");
        subText.setAttribute("x", c.x + 12);
        subText.setAttribute("y", c.y + 71);
        subText.setAttribute("font-family", "JetBrains Mono, monospace");
        subText.setAttribute("font-size", "9");
        subText.setAttribute("fill", "rgba(255,255,255,0.4)");
        subText.textContent = `${t.id} • ${t.dependencies && t.dependencies.length ? t.dependencies.length + ' dep(s)' : 'root step'}`;
        g.appendChild(subText);

        svg.appendChild(g);
    });
}

// ─── NODE INSPECTOR (OPAL MODAL) ─────────────────────────────────
function openNodeInspector(taskId) {
    if (!window.latestTasks || !window.latestTasks[taskId]) return;
    const task = window.latestTasks[taskId];

    const modal = document.getElementById("opal-inspector-modal");
    if (!modal) return;

    const emojiMap = {
        researcher: "🔍",
        analyzer: "📊",
        critic: "🛡️",
        planner: "🗺️",
        intent_analyzer: "🤖",
        synthesizer: "📑"
    };

    const roleMap = {
        researcher: "WEB INTELLIGENCE & RESEARCH",
        analyzer: "DATA MODELING & SANDBOX MATH",
        critic: "SECURITY & QUALITY AUDITOR",
        planner: "TASK DAG ARCHITECT",
        intent_analyzer: "INTENT CLASSIFIER",
        synthesizer: "STRATEGIC REPORT COMPILER"
    };

    const agentKey = (task.assigned_agent || "researcher").toLowerCase();

    // 1. Agent Icon & Titles
    const agentIconEl = document.getElementById("insp-agent-icon");
    if (agentIconEl) agentIconEl.textContent = emojiMap[agentKey] || "⚙️";

    const titleEl = document.getElementById("insp-task-title");
    if (titleEl) titleEl.textContent = task.title || task.id;

    const roleEl = document.getElementById("insp-agent-role");
    if (roleEl) roleEl.textContent = roleMap[agentKey] || agentKey.toUpperCase();

    // 2. Status Badge
    const badge = document.getElementById("insp-status-badge");
    if (badge) {
        const st = (task.status || "pending").toLowerCase();
        if (st === "completed") {
            badge.className = "status-pill status-done";
            badge.textContent = "✓ Completed";
        } else if (st === "running") {
            badge.className = "status-pill status-running";
            badge.textContent = "⚡ Running";
        } else if (st === "failed") {
            badge.className = "status-pill status-error";
            badge.textContent = "✗ Failed";
        } else {
            badge.className = "status-pill status-idle";
            badge.textContent = "⌛ Queued";
        }
    }

    // 3. Specialist Persona Badge
    const personaBadge = document.getElementById("insp-persona-badge");
    if (personaBadge) {
        const pName = (window.latestPersonaMeta && window.latestPersonaMeta.name) || window.latestPersona;
        const pEmoji = (window.latestPersonaMeta && window.latestPersonaMeta.emoji) || "🤖";
        const pDiv = (window.latestPersonaMeta && window.latestPersonaMeta.division) || "";
        if (pName) {
            personaBadge.style.display = "inline-flex";
            personaBadge.textContent = `${pEmoji} ${pName}${pDiv ? ' (' + pDiv + ')' : ''}`;
        } else {
            personaBadge.style.display = "none";
        }
    }

    // 4. Capability / Skill Badge
    const skillBadge = document.getElementById("insp-skill-badge");
    if (skillBadge) {
        const skills = window.latestSkills || [];
        if (skills.length > 0) {
            const formatted = formatSkill(skills[0]);
            if (formatted) {
                skillBadge.style.display = "inline-flex";
                skillBadge.textContent = `${formatted.icon} ${formatted.text}`;
            } else {
                skillBadge.style.display = "none";
            }
        } else {
            skillBadge.style.display = "none";
        }
    }

    // 5. Metadata Items (Task ID, Latency, Dependencies, Retries)
    const taskIdEl = document.getElementById("insp-task-id");
    if (taskIdEl) taskIdEl.textContent = task.id || "—";

    const latencyEl = document.getElementById("insp-latency");
    if (latencyEl) {
        let latency = null;
        if (window.latestTraces && Array.isArray(window.latestTraces)) {
            const matchTrace = window.latestTraces.find(tr => tr.task_id === task.id || tr.agent === task.assigned_agent || (tr.name && tr.name.includes(task.title)));
            if (matchTrace && matchTrace.duration_sec !== undefined) {
                latency = matchTrace.duration_sec;
            }
        }
        latencyEl.textContent = latency !== null ? `${latency.toFixed(2)}s` : "—";
    }

    const depsEl = document.getElementById("insp-deps");
    if (depsEl) {
        const deps = task.dependencies || [];
        depsEl.textContent = deps.length ? deps.join(", ") : "None (Root Step)";
    }

    const retriesEl = document.getElementById("insp-retries");
    if (retriesEl) {
        retriesEl.textContent = `${task.retries || 0} / ${task.max_retries || 3}`;
    }

    // 6. Subtask Description
    const descEl = document.getElementById("insp-desc");
    if (descEl) descEl.textContent = task.description || "No description provided.";

    // 7. Output String and Inspection
    const outputStr = task.output || task.error || "";

    // 8. Python Sandbox Code Executed (Analyzer / Sandbox Tasks)
    const codeSection = document.getElementById("insp-code-section");
    const codePre = document.getElementById("insp-code");
    let extractedCode = task.code_executed || (task.data && task.data.code_executed) || null;

    if (!extractedCode && outputStr) {
        const codeBlockMatch = outputStr.match(/```(?:python|py)?\r?\n([\s\S]*?)```/);
        if (codeBlockMatch) {
            extractedCode = codeBlockMatch[1].trim();
        }
    }

    if (extractedCode && codeSection && codePre) {
        codeSection.style.display = "block";
        codePre.textContent = extractedCode;
    } else if (codeSection) {
        codeSection.style.display = "none";
    }

    // 9. Quantitative Sandbox Metrics
    const metricsSection = document.getElementById("insp-metrics-section");
    const metricsGrid = document.getElementById("insp-metrics-grid");
    let extractedMetrics = task.calculated_metrics || (task.data && task.data.calculated_metrics) || null;

    if (!extractedMetrics && outputStr) {
        const metricsMatch = outputStr.match(/Calculated metrics:\s*(\{.*?\})/);
        if (metricsMatch) {
            try {
                const jsonStr = metricsMatch[1].replace(/'/g, '"');
                extractedMetrics = JSON.parse(jsonStr);
            } catch (err) {
                console.debug("[Inspector] Metric parse fallback error:", err);
            }
        }
    }

    if (extractedMetrics && typeof extractedMetrics === "object" && Object.keys(extractedMetrics).length > 0 && metricsSection && metricsGrid) {
        metricsSection.style.display = "block";
        metricsGrid.innerHTML = "";
        Object.entries(extractedMetrics).forEach(([k, v]) => {
            const card = document.createElement("div");
            card.className = "metric-card";
            const valFormatted = typeof v === "number" ? (Number.isInteger(v) ? v.toLocaleString() : v.toFixed(3)) : String(v);
            card.innerHTML = `
                <span class="metric-card-label">${escHtml(k.replace(/_/g, ' '))}</span>
                <span class="metric-card-val">${escHtml(valFormatted)}</span>
            `;
            metricsGrid.appendChild(card);
        });
    } else if (metricsSection) {
        metricsSection.style.display = "none";
    }

    // 10. Output Findings & Computations
    const outputEl = document.getElementById("insp-output");
    if (outputEl) {
        if (task.error) {
            outputEl.textContent = `Error: ${task.error}`;
            outputEl.style.color = "#fca5a5";
        } else {
            outputEl.textContent = outputStr || "Task execution has not completed yet or returned no output.";
            outputEl.style.color = "";
        }
    }

    modal.classList.remove("hidden");
}

function closeNodeInspector() {
    const modal = document.getElementById("opal-inspector-modal");
    if (modal) modal.classList.add("hidden");
}

function closeInspectorOnBackdrop(e) {
    if (e.target.id === "opal-inspector-modal") {
        closeNodeInspector();
    }
}

function copyInspectorCode() {
    const codeEl = document.getElementById("insp-code");
    if (!codeEl) return;
    navigator.clipboard.writeText(codeEl.textContent).then(() => {
        const label = document.getElementById("copy-code-label");
        if (label) {
            label.textContent = "Copied!";
            setTimeout(() => { label.textContent = "Copy"; }, 2000);
        }
    });
}

function copyInspectorOutput() {
    const outputEl = document.getElementById("insp-output");
    if (!outputEl) return;
    navigator.clipboard.writeText(outputEl.textContent).then(() => {
        const label = document.getElementById("copy-output-label");
        if (label) {
            label.textContent = "Copied!";
            setTimeout(() => { label.textContent = "Copy"; }, 2000);
        }
    });
}

// ─── TIMELINE WATERFALL ──────────────────────────────────────────
function plotTimeline(traces) {
    const box = document.getElementById("timeline-waterfall-box");
    if (!box) return;
    if (!traces.length) {
        box.innerHTML = `<div class="report-empty" style="height:220px">
            <i class="fa-solid fa-chart-gantt"></i>
            <p>Execute a research workflow to view microsecond execution timeline</p></div>`;
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
        const width = Math.max((span.duration_sec||0) / total * 100, 3).toFixed(1);
        const color = agentColors[span.agent] || "#6366f1";
        const row   = document.createElement("div");
        row.className = "gantt-row";
        row.innerHTML = `
            <div class="gantt-label" title="${span.name || span.agent}">${span.name || span.agent}</div>
            <div class="gantt-track">
                <div class="gantt-bar" style="left:${left}%;width:${width}%;background:${color}">
                    <span style="font-size:9.5px;color:#fff;font-weight:600">${(span.duration_sec||0).toFixed(2)}s</span>
                </div>
            </div>`;
        box.appendChild(row);
    });
}

// ─── SESSION HISTORY ─────────────────────────────────────────────
async function loadSessionHistory() {
    const list = document.getElementById("session-history-list");
    if (!list) return;
    try {
        const res     = await fetch("/api/sessions");
        const data    = await res.json();
        const sessions = (data.sessions || []).slice(0, 10);
        if (!sessions.length) { list.innerHTML = `<div class="history-empty">No archived sessions yet</div>`; return; }
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
            
            item.addEventListener("click", () => loadArchivedReport(s.session_id));
            
            const delBtn = item.querySelector(".btn-delete");
            if (delBtn) {
                delBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    deleteSession(s.session_id, item);
                });
            }
            list.appendChild(item);
        });
    } catch(e) { console.error("History load error:", e); }
}

async function loadArchivedReport(sessionId) {
    try {
        const res = await fetch(`/api/report/${sessionId}`);
        if (!res.ok) { alert("Report not found."); return; }
        const data = await res.json();
        activeSessionId = sessionId;
        currentReportMd = data.report || data.content || "";
        
        // Restore tasks, traces, and DAG state
        window.latestTasks = data.tasks || {};
        window.latestTraces = data.traces || [];
        
        renderReport(currentReportMd);
        renderActiveSkills(data.active_skills || []);
        
        if (data.tasks && Object.keys(data.tasks).length > 0) {
            plotGraph(data.tasks, "synthesizer");
        }
        if (data.traces && data.traces.length > 0) {
            plotTimeline(data.traces);
        }
        if (data.logs && data.logs.length > 0) {
            const stream = document.getElementById("terminal-thought-stream");
            if (stream) stream.innerHTML = "";
            logCount = 0;
            renderLogs(data.logs);
        }

        switchTab("report-tab");
        
        const metaHeader = document.getElementById("report-meta-header");
        if (metaHeader) metaHeader.style.display = "flex";
        const metaSess = document.getElementById("meta-session-id");
        if (metaSess) metaSess.textContent = `Archived Session: ${sessionId.slice(0,8)}`;
        const metaConf = document.getElementById("meta-confidence");
        if (metaConf) metaConf.textContent = `Audit Score: ${(data.confidence_score||0).toFixed(2)} / 1.00`;

        // Restore Phase 5 Stepper, Pod Visualizer, Evidence Inspector, and Telemetry
        const archivedState = {
            status: "completed",
            active_agent: "synthesizer",
            tasks: data.tasks || {},
            traces: data.traces || [],
            working_memory: { final_report: currentReportMd },
            assigned_persona: data.persona || null,
            persona_meta: null,
            metrics: { replanning_cycle_count: 0 }
        };
        updateExecutiveStepper(archivedState);
        updateAgencyPodVisualizer(archivedState);
        updateTelemetryStats(archivedState);
        renderEvidenceInspector(sessionId);

        const msgEl = document.getElementById("stepper-status-msg");
        if (msgEl) {
            msgEl.textContent = "Stage 9/9 [FINAL DOSSIER]: Archived dossier loaded with verified claim-level provenance.";
        }
    } catch(e) { alert(`Could not load report: ${e}`); }
}

async function deleteSession(id, element) {
    try {
        const res = await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
        if (res.ok && element) {
            element.remove();
        }
    } catch(e) { console.error("deleteSession error:", e); }
}

// ─── ACTION BUTTONS (COPY, PDF, MD, EXPORTS) ─────────────────────
function copyReportMarkdown() {
    if (!currentReportMd) { alert("No report generated yet."); return; }
    navigator.clipboard.writeText(currentReportMd).then(() => {
        const btn = document.querySelector(".action-btn");
        if (btn) {
            btn.innerHTML = `<i class="fa-solid fa-check"></i> <span>Copied!</span>`;
            setTimeout(() => {
                btn.innerHTML = `<i class="fa-solid fa-copy"></i> <span>Copy</span>`;
            }, 2000);
        }
    });
}

function exportToPDF() {
    if (!currentReportMd) { alert("No report to export."); return; }
    window.print();
}

function downloadReport() {
    if (!currentReportMd) { alert("No report to download."); return; }
    const blob = new Blob([currentReportMd], { type: "text/markdown" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `neuroweave_brief_${(activeSessionId||"").slice(0,8)}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

// ─── KNOWLEDGE UPLOAD & INGESTION ────────────────────────────────
async function handleFileUpload(file) {
    if (!file) return;
    const statusEl = document.getElementById("upload-status");
    if (statusEl) statusEl.textContent = `Uploading ${file.name}...`;
    const fd = new FormData();
    fd.append("file", file);
    try {
        const res  = await fetch("/api/upload", { method: "POST", body: fd });
        const data = await res.json();
        if (data.success && statusEl) {
            statusEl.textContent = `✓ Ingested into Knowledge Vault: ${file.name}`;
            statusEl.style.color = "#10b981";
        }
    } catch(e) {
        if (statusEl) {
            statusEl.textContent = `✗ Error: ${e}`;
            statusEl.style.color = "#ef4444";
        }
    }
}

async function ingestUrlAction() {
    const input = document.getElementById("url-input");
    const url = input ? input.value.trim() : "";
    const statusEl = document.getElementById("upload-status");
    if (!url) { alert("Please enter a URL to ingest."); return; }
    if (statusEl) statusEl.textContent = `Scraping & Ingesting ${url}...`;
    try {
        const res = await fetch('/api/ingest-url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, session_id: activeSessionId || "global" })
        });
        const data = await res.json();
        if (data.success && statusEl) {
            statusEl.textContent = `✓ Successfully Ingested Webpage into Semantic Memory!`;
            statusEl.style.color = "#10b981";
            if (input) input.value = "";
        }
    } catch(e) {
        if (statusEl) {
            statusEl.textContent = `✗ Failed to ingest URL: ${e}`;
            statusEl.style.color = "#ef4444";
        }
    }
}

// ─── SPEECH RECOGNITION ──────────────────────────────────────────
document.addEventListener("click", (e) => {
    const micBtn = e.target.closest("#mic-btn");
    if (micBtn) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            alert("Speech recognition is not supported in this browser.");
            return;
        }

        if (isSpeechRecording) {
            if (speechRecognitionInstance) speechRecognitionInstance.stop();
            micBtn.classList.remove("recording");
            isSpeechRecording = false;
        } else {
            speechRecognitionInstance = new SpeechRecognition();
            speechRecognitionInstance.onstart = () => {
                micBtn.classList.add("recording");
                isSpeechRecording = true;
            };
            speechRecognitionInstance.onresult = (event) => {
                const queryInput = document.getElementById("query-input");
                if (queryInput) queryInput.value = event.results[0][0].transcript;
            };
            speechRecognitionInstance.onend = () => {
                micBtn.classList.remove("recording");
                isSpeechRecording = false;
            };
            speechRecognitionInstance.start();
        }
    }
});

// ─── GLOBAL WINDOW EXPORTS ───────────────────────────────────────
window.triggerWorkflow = triggerWorkflow;
window.setDivision = setDivision;
window.setQuery = setQuery;
window.toggleLogs = toggleLogs;
window.toggleSection = toggleSection;
window.switchTab = switchTab;
window.saveApiKey = saveApiKey;
window.handleProviderChange = handleProviderChange;
window.copyReportMarkdown = copyReportMarkdown;
window.exportToPDF = exportToPDF;
window.downloadReport = downloadReport;
window.exportEvidenceJSON = exportEvidenceJSON;
window.exportFlowJSON = exportFlowJSON;
window.exportSessionJSON = exportSessionJSON;
window.filterEvidence = filterEvidence;
window.renderEvidenceInspector = renderEvidenceInspector;
window.ingestUrlAction = ingestUrlAction;
window.loadSessionHistory = loadSessionHistory;
window.openNodeInspector = openNodeInspector;
window.closeNodeInspector = closeNodeInspector;
window.closeInspectorOnBackdrop = closeInspectorOnBackdrop;
window.copyInspectorCode = copyInspectorCode;
window.copyInspectorOutput = copyInspectorOutput;
window.copyCodeBlock = copyCodeBlock;
window.plotGraph = plotGraph;
window.renderReport = renderReport;
window.renderActiveSkills = renderActiveSkills;

