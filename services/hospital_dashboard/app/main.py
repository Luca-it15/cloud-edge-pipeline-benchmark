import json
import os
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse


DATASET_PATH = Path(os.getenv("DATASET_PATH", "/app/data/patients.json"))
RESULTS_PATH = Path(os.getenv("RESULTS_PATH", "/app/results/patient_results.json"))
PORT = int(os.getenv("PORT", "8080"))
BENCHMARK_API_URL = os.getenv("BENCHMARK_API_URL", "http://benchmark-api:8090").rstrip("/")


app = FastAPI(title="Hospital Operations Dashboard", version="1.0.0")


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def base_payload() -> dict[str, Any]:
    patients = read_json(DATASET_PATH, [])
    patient_payload = []
    risk_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "pending": len(patients)}
    ward_counts: dict[str, dict[str, int]] = {}

    for patient in patients:
        ward_counts.setdefault(patient["ward"], {"patients": 0, "alerts": 0})
        ward_counts[patient["ward"]]["patients"] += 1
        patient_payload.append(
            {
                "patient_id": patient["patient_id"],
                "name": patient["name"],
                "age": patient["age"],
                "sex": patient["sex"],
                "ward": patient["ward"],
                "bed": patient["bed"],
                "diagnosis": patient["primary_diagnosis"],
                "comorbidities": patient.get("comorbidities", []),
                "medications": patient.get("medications", []),
                "latest_vitals": patient["vitals"][-1],
                "initial_risk_score": None,
                "initial_risk_level": "pending",
                "risk_score": None,
                "risk_level": "pending",
                "recommended_action": "Waiting for pipeline response",
                "abnormal_vitals": [],
                "alert": False,
                "pipeline_comparison": {},
            }
        )

    return {
        "generated_at": None,
        "dataset_size": len(patients),
        "scenarios": [],
        "summary": {},
        "risk_counts": risk_counts,
        "ward_counts": ward_counts,
        "patients": sorted(
            patient_payload,
            key=lambda item: (item["ward"], item["bed"], item["name"]),
        ),
        "results": [],
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/patient-results")
async def patient_results(pending: bool = False) -> dict[str, Any]:
    if pending:
        return base_payload()
    if RESULTS_PATH.exists():
        return read_json(RESULTS_PATH, {})
    return base_payload()


@app.get("/api/benchmark/status")
async def benchmark_status() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{BENCHMARK_API_URL}/status")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Benchmark API unavailable: {exc}") from exc


@app.post("/api/benchmark/run")
async def benchmark_run() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(f"{BENCHMARK_API_URL}/run", json={})
            if response.status_code == 409:
                raise HTTPException(status_code=409, detail="Benchmark is already running")
            response.raise_for_status()
            return response.json()
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Benchmark API unavailable: {exc}") from exc


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return DASHBOARD_HTML


DASHBOARD_HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hospital Pipeline Dashboard</title>
  <style>
    :root {
      --bg: #f6f8fb;
      --surface: #ffffff;
      --line: #d8e0e8;
      --text: #17212b;
      --muted: #617080;
      --accent: #0f6b8f;
      --accent-2: #2b7a4b;
      --critical: #b42318;
      --high: #c25500;
      --medium: #927000;
      --low: #257248;
      --pending: #667085;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, Arial, Helvetica, sans-serif;
      font-size: 14px;
      letter-spacing: 0;
    }

    header {
      background: var(--surface);
      border-bottom: 1px solid var(--line);
    }

    .shell {
      width: min(1440px, calc(100vw - 32px));
      margin: 0 auto;
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      min-height: 72px;
      gap: 20px;
    }

    h1 {
      margin: 0;
      font-size: 22px;
      line-height: 1.2;
      font-weight: 760;
    }

    .subtle {
      color: var(--muted);
      font-size: 13px;
    }

    .toolbar {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }

    select, input, button {
      height: 36px;
      border: 1px solid var(--line);
      background: var(--surface);
      color: var(--text);
      border-radius: 6px;
      padding: 0 10px;
      font: inherit;
    }

    button {
      background: var(--accent);
      color: white;
      border-color: var(--accent);
      cursor: pointer;
      font-weight: 700;
    }

    button:disabled {
      cursor: not-allowed;
      opacity: 0.62;
    }

    .status-pill {
      min-height: 36px;
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 0 12px;
      background: #fbfcfe;
      color: var(--muted);
      font-size: 12px;
      font-weight: 760;
      text-transform: uppercase;
    }

    .status-pill.running { color: var(--accent); border-color: #9bc8d9; background: #eef7fb; }
    .status-pill.completed { color: var(--low); border-color: #a8d7ba; background: #effaf3; }
    .status-pill.failed { color: var(--critical); border-color: #e3aaa5; background: #fff2f0; }
    .status-pill.unavailable { color: var(--high); border-color: #efc69c; background: #fff7ed; }

    main {
      padding: 18px 0 26px;
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(5, minmax(150px, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }

    .metric {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-height: 92px;
    }

    .metric .label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }

    .metric .value {
      margin-top: 8px;
      font-size: 28px;
      font-weight: 780;
    }

    .latency-panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-bottom: 16px;
      overflow: hidden;
    }

    .latency-table th,
    .latency-table td {
      padding: 9px 12px;
    }

    .latency-name {
      font-weight: 780;
    }

    .latency-empty {
      padding: 14px;
      color: var(--muted);
    }

    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1.55fr) minmax(360px, 0.9fr);
      gap: 16px;
      align-items: start;
    }

    section {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }

    .section-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfe;
    }

    .section-head h2 {
      margin: 0;
      font-size: 15px;
      line-height: 1.2;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }

    th, td {
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }

    th {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      background: #fbfcfe;
    }

    tbody tr {
      cursor: pointer;
    }

    tbody tr:hover {
      background: #f5f9fc;
    }

    .risk {
      display: inline-flex;
      align-items: center;
      min-width: 76px;
      justify-content: center;
      padding: 4px 8px;
      border-radius: 999px;
      color: white;
      font-size: 12px;
      font-weight: 760;
      text-transform: uppercase;
    }

    .risk.critical { background: var(--critical); }
    .risk.high { background: var(--high); }
    .risk.medium { background: var(--medium); }
    .risk.low { background: var(--low); }
    .risk.pending { background: var(--pending); }

    .detail {
      padding: 14px;
    }

    .patient-title {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: flex-start;
      margin-bottom: 10px;
    }

    .patient-title h3 {
      margin: 0;
      font-size: 18px;
    }

    .kv {
      display: grid;
      grid-template-columns: 130px minmax(0, 1fr);
      gap: 8px 12px;
      margin: 12px 0;
    }

    .kv .k {
      color: var(--muted);
      font-weight: 700;
    }

    .vitals {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      margin-top: 10px;
    }

    .vital {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px;
      min-height: 68px;
      background: #fbfcfe;
    }

    .vital .name {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }

    .vital .number {
      margin-top: 5px;
      font-size: 20px;
      font-weight: 760;
    }

    .bars {
      padding: 14px;
    }

    .bar-row {
      display: grid;
      grid-template-columns: 150px 1fr 72px;
      align-items: center;
      gap: 10px;
      margin: 8px 0;
    }

    .bar-track {
      height: 10px;
      background: #edf2f7;
      border-radius: 999px;
      overflow: hidden;
    }

    .bar-fill {
      height: 100%;
      background: var(--accent);
      border-radius: 999px;
    }

    .comparison {
      margin-top: 12px;
      border-top: 1px solid var(--line);
      padding-top: 12px;
    }

    .comparison-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }

    .comparison-item {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
      background: #fbfcfe;
      min-height: 84px;
    }

    .comparison-item .name {
      font-weight: 780;
      margin-bottom: 6px;
    }

    .mono {
      font-family: Consolas, "Courier New", monospace;
      font-size: 12px;
    }

    .critical-dialog-backdrop {
      position: fixed;
      inset: 0;
      z-index: 20;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 18px;
      background: rgba(15, 23, 42, 0.52);
    }

    .critical-dialog-backdrop.open {
      display: flex;
    }

    .critical-dialog {
      width: min(560px, 100%);
      background: var(--surface);
      border: 2px solid var(--critical);
      border-radius: 8px;
      box-shadow: 0 24px 70px rgba(15, 23, 42, 0.28);
      overflow: hidden;
    }

    .critical-dialog-head {
      padding: 14px 16px;
      background: #fff2f0;
      border-bottom: 1px solid #e3aaa5;
    }

    .critical-dialog-head h2 {
      margin: 0;
      color: var(--critical);
      font-size: 18px;
    }

    .critical-dialog-body {
      padding: 14px 16px;
    }

    .critical-dialog-list {
      margin: 12px 0 0;
      padding: 0;
      list-style: none;
      max-height: 260px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 6px;
    }

    .critical-dialog-list li {
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
    }

    .critical-dialog-list li:last-child {
      border-bottom: 0;
    }

    .critical-dialog-foot {
      display: flex;
      justify-content: flex-end;
      gap: 10px;
      padding: 12px 16px;
      border-top: 1px solid var(--line);
      background: #fbfcfe;
    }

    .critical-dialog-foot button {
      background: var(--critical);
      border-color: var(--critical);
    }

    @media (max-width: 1050px) {
      .metrics { grid-template-columns: repeat(2, minmax(150px, 1fr)); }
      .layout { grid-template-columns: 1fr; }
    }

    @media (max-width: 700px) {
      .shell { width: min(100vw - 18px, 1440px); }
      .topbar { align-items: flex-start; flex-direction: column; padding: 12px 0; }
      .metrics { grid-template-columns: 1fr; }
      th:nth-child(4), td:nth-child(4) { display: none; }
      .vitals, .comparison-grid { grid-template-columns: 1fr; }
      .bar-row { grid-template-columns: 108px 1fr 54px; }
    }
  </style>
</head>
<body>
  <header>
    <div class="shell topbar">
      <div>
        <h1>Hospital Pipeline Dashboard</h1>
        <div class="subtle" id="generatedAt">Waiting for benchmark data</div>
      </div>
      <div class="toolbar">
        <select id="wardFilter" aria-label="Filter by ward"></select>
        <select id="riskFilter" aria-label="Filter by risk">
          <option value="all">All risk levels</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
          <option value="pending">Pending</option>
        </select>
        <input id="searchBox" type="search" placeholder="Search patient, bed, diagnosis">
        <button id="runBenchmarkButton">Run benchmark</button>
        <span class="status-pill" id="benchmarkStatus">Idle</span>
        <button id="refreshButton">Refresh</button>
      </div>
    </div>
  </header>

  <main class="shell">
    <div class="metrics">
      <div class="metric"><div class="label">Patients</div><div class="value" id="metricPatients">0</div></div>
      <div class="metric"><div class="label">Critical</div><div class="value" id="metricCritical">0</div></div>
      <div class="metric"><div class="label">High Risk</div><div class="value" id="metricHigh">0</div></div>
      <div class="metric"><div class="label">Alerts</div><div class="value" id="metricAlerts">0</div></div>
      <div class="metric"><div class="label">Scenarios</div><div class="value" id="metricScenarios">0</div></div>
    </div>

    <section class="latency-panel">
      <div class="section-head">
        <h2>Pipeline Latency</h2>
        <span class="subtle">Round-trip measurements from dashboard/runner to each system</span>
      </div>
      <div id="latencyPanel"></div>
    </section>

    <div class="layout">
      <section>
        <div class="section-head">
          <h2>Patient Worklist</h2>
          <span class="subtle" id="tableCount">0 visible</span>
        </div>
        <table>
          <thead>
            <tr>
              <th style="width: 96px;">Risk</th>
              <th>Patient</th>
              <th style="width: 150px;">Location</th>
              <th>Diagnosis</th>
              <th style="width: 90px;">Score</th>
            </tr>
          </thead>
          <tbody id="patientRows"></tbody>
        </table>
      </section>

      <div>
        <section>
          <div class="section-head">
            <h2>Selected Patient</h2>
            <span class="subtle">Clinical summary</span>
          </div>
          <div class="detail" id="patientDetail"></div>
        </section>

        <section style="margin-top:16px;">
          <div class="section-head">
            <h2>Ward Load</h2>
            <span class="subtle">Patients and active alerts</span>
          </div>
          <div class="bars" id="wardBars"></div>
        </section>
      </div>
    </div>
  </main>

  <div class="critical-dialog-backdrop" id="criticalDialog" role="dialog" aria-modal="true" aria-labelledby="criticalDialogTitle">
    <div class="critical-dialog">
      <div class="critical-dialog-head">
        <h2 id="criticalDialogTitle">Pazienti critici rilevati</h2>
      </div>
      <div class="critical-dialog-body">
        <strong>Ci sono pazienti con valori critici. Intervenire subito.</strong>
        <ul class="critical-dialog-list" id="criticalDialogList"></ul>
      </div>
      <div class="critical-dialog-foot">
        <button id="criticalDialogClose">Ho preso visione</button>
      </div>
    </div>
  </div>

  <script>
    let state = { patients: [], ward_counts: {}, risk_counts: {}, summary: {}, scenarios: [] };
    let benchmarkState = { status: "idle", running: false };
    let selectedPatientId = null;
    let statusPoll = null;

    const riskOrder = { critical: 0, high: 1, medium: 2, low: 3, pending: 4 };
    const pipelineLabels = {
      cloud: "Google Cloud Run",
      edge: "Edge HTTP",
      edge_tls: "Edge TLS",
      cloud_tls: "Cloud TLS",
    };

    function riskBadge(level) {
      const normalized = level || "pending";
      return `<span class="risk ${normalized}">${normalized}</span>`;
    }

    function fmtMs(value) {
      if (value === undefined || value === null) return "n/a";
      return `${Number(value).toFixed(1)} ms`;
    }

    function fmtKb(value) {
      if (value === undefined || value === null) return "n/a";
      return `${Number(value).toFixed(2)} KB`;
    }

    function latestVitalsHtml(vitals) {
      const items = [
        ["HR", vitals.heart_rate, "bpm"],
        ["SBP", vitals.systolic_bp, "mmHg"],
        ["RR", vitals.respiratory_rate, "/min"],
        ["SpO2", vitals.spo2, "%"],
        ["Temp", vitals.temperature, "C"],
        ["Glucose", vitals.glucose, "mg/dL"],
      ];
      return `<div class="vitals">${items.map(([name, value, unit]) => `
        <div class="vital"><div class="name">${name}</div><div class="number">${value} <span class="subtle">${unit}</span></div></div>
      `).join("")}</div>`;
    }

    function comparisonHtml(patient) {
      const entries = Object.entries(patient.pipeline_comparison || {});
      if (!entries.length) return `<div class="subtle">Run the benchmark to populate pipeline comparison.</div>`;
      return `<div class="comparison"><h3>Pipeline comparison</h3><div class="comparison-grid">${entries.map(([name, data]) => `
        <div class="comparison-item">
          <div class="name">${pipelineLabels[name] || name}</div>
          <div class="mono">round trip: ${fmtMs(data.client_total_ms)}</div>
          <div class="mono">service: ${fmtMs(data.service_total_ms)}</div>
          <div class="mono">transport: ${data.transport_security || "plain"}</div>
          <div class="mono">payload: ${fmtKb(data.payload_sent_kb)}</div>
          <div class="mono">risk: ${(data.risk_level || "n/a").toUpperCase()} (${data.risk_score ?? "n/a"})</div>
        </div>
      `).join("")}</div></div>`;
    }

    function renderDetail(patient) {
      const target = document.getElementById("patientDetail");
      if (!patient) {
        target.innerHTML = `<div class="subtle">Select a patient from the worklist.</div>`;
        return;
      }
      target.innerHTML = `
        <div class="patient-title">
          <div>
            <h3>${patient.name}</h3>
            <div class="subtle">${patient.patient_id} · ${patient.age} ${patient.sex} · ${patient.ward} ${patient.bed}</div>
          </div>
          ${riskBadge(patient.risk_level)}
        </div>
        <div class="kv">
          <div class="k">Diagnosis</div><div>${patient.diagnosis}</div>
          <div class="k">Initial risk</div><div>${(patient.initial_risk_level || patient.risk_level || "pending").toUpperCase()} (${patient.initial_risk_score ?? patient.risk_score ?? "pending"})</div>
          <div class="k">Risk score</div><div>${patient.risk_score ?? "pending"}</div>
          <div class="k">Action</div><div>${patient.recommended_action}</div>
          <div class="k">Out of range</div><div>${(patient.abnormal_vitals || []).length ? patient.abnormal_vitals.map((item) => `${item.vital} ${item.value}${item.unit}`).join(", ") : "None"}</div>
          <div class="k">Comorbidities</div><div>${patient.comorbidities.length ? patient.comorbidities.join(", ") : "None recorded"}</div>
          <div class="k">Medications</div><div>${patient.medications.length ? patient.medications.join(", ") : "None recorded"}</div>
        </div>
        ${latestVitalsHtml(patient.latest_vitals)}
        ${comparisonHtml(patient)}
      `;
    }

    function filteredPatients() {
      const ward = document.getElementById("wardFilter").value;
      const risk = document.getElementById("riskFilter").value;
      const query = document.getElementById("searchBox").value.trim().toLowerCase();
      return state.patients.filter((patient) => {
        const wardOk = ward === "all" || patient.ward === ward;
        const riskOk = risk === "all" || patient.risk_level === risk;
        const queryText = `${patient.name} ${patient.patient_id} ${patient.ward} ${patient.bed} ${patient.diagnosis}`.toLowerCase();
        return wardOk && riskOk && (!query || queryText.includes(query));
      }).sort((a, b) => (riskOrder[a.risk_level] ?? 9) - (riskOrder[b.risk_level] ?? 9) || a.ward.localeCompare(b.ward));
    }

    function renderRows() {
      const rows = filteredPatients();
      const tbody = document.getElementById("patientRows");
      document.getElementById("tableCount").textContent = `${rows.length} visible`;
      tbody.innerHTML = rows.map((patient) => `
        <tr data-patient-id="${patient.patient_id}">
          <td>${riskBadge(patient.risk_level)}</td>
          <td><strong>${patient.name}</strong><div class="subtle">${patient.patient_id}</div></td>
          <td>${patient.ward}<div class="subtle">${patient.bed}</div></td>
          <td>${patient.diagnosis}</td>
          <td><strong>${patient.risk_score ?? "pending"}</strong></td>
        </tr>
      `).join("");
      tbody.querySelectorAll("tr").forEach((row) => {
        row.addEventListener("click", () => {
          selectedPatientId = row.dataset.patientId;
          render();
        });
      });
      if (!selectedPatientId && rows.length) selectedPatientId = rows[0].patient_id;
    }

    function renderLatencyPanel() {
      const target = document.getElementById("latencyPanel");
      const preferred = ["cloud", "edge", "edge_tls"];
      const summary = state.summary || {};
      const rows = preferred
        .filter((name) => summary[name])
        .map((name) => [name, summary[name]])
        .concat(
          Object.entries(summary).filter(([name]) => !preferred.includes(name))
        );

      if (!rows.length) {
        target.innerHTML = `<div class="latency-empty">Run the benchmark to populate p99 latency for Google Cloud, Edge HTTP and Edge TLS.</div>`;
        return;
      }

      target.innerHTML = `
        <table class="latency-table">
          <thead>
            <tr>
              <th>System</th>
              <th>Runs</th>
              <th>Mean round trip</th>
              <th>P99 round trip</th>
              <th>Mean service</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(([name, data]) => `
              <tr>
                <td class="latency-name">${pipelineLabels[name] || name}</td>
                <td>${data.runs ?? 0}</td>
                <td>${fmtMs(data.client_total_ms?.mean)}</td>
                <td><strong>${fmtMs(data.client_total_ms?.p99)}</strong></td>
                <td>${fmtMs((data.mean_preprocess_ms || 0) + (data.mean_inference_ms || 0) + (data.mean_storage_ms || 0) + (data.mean_sync_ms || 0))}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      `;
    }

    function renderWardBars() {
      const target = document.getElementById("wardBars");
      const entries = Object.entries(state.ward_counts || {}).sort((a, b) => b[1].alerts - a[1].alerts || b[1].patients - a[1].patients);
      const maxPatients = Math.max(1, ...entries.map(([, value]) => value.patients));
      target.innerHTML = entries.map(([ward, value]) => `
        <div class="bar-row">
          <div>${ward}</div>
          <div class="bar-track"><div class="bar-fill" style="width:${(value.patients / maxPatients) * 100}%"></div></div>
          <div class="mono">${value.patients} / ${value.alerts}</div>
        </div>
      `).join("") || `<div class="subtle">No ward data available.</div>`;
    }

    function renderMetrics() {
      const risk = state.risk_counts || {};
      const alerts = state.patients.filter((patient) => patient.alert).length;
      document.getElementById("metricPatients").textContent = state.patients.length;
      document.getElementById("metricCritical").textContent = risk.critical || 0;
      document.getElementById("metricHigh").textContent = risk.high || 0;
      document.getElementById("metricAlerts").textContent = alerts;
      document.getElementById("metricScenarios").textContent = state.scenarios.length || 0;
      document.getElementById("generatedAt").textContent = state.generated_at
        ? `Last benchmark: ${state.generated_at}`
        : "Benchmark not run yet";
    }

    function renderFilters() {
      const select = document.getElementById("wardFilter");
      const current = select.value || "all";
      const wards = [...new Set(state.patients.map((patient) => patient.ward))].sort();
      select.innerHTML = `<option value="all">All wards</option>` + wards.map((ward) => `<option value="${ward}">${ward}</option>`).join("");
      select.value = wards.includes(current) ? current : "all";
    }

    function render() {
      renderFilters();
      renderMetrics();
      renderLatencyPanel();
      renderRows();
      renderWardBars();
      const selected = state.patients.find((patient) => patient.patient_id === selectedPatientId) || filteredPatients()[0];
      renderDetail(selected);
    }

    async function loadData(options = {}) {
      const url = options.pending ? "/api/patient-results?pending=true" : "/api/patient-results";
      const response = await fetch(url, { cache: "no-store" });
      state = await response.json();
      render();
    }

    function resetDashboardForRun() {
      state.generated_at = null;
      state.scenarios = [];
      state.summary = {};
      state.risk_counts = { critical: 0, high: 0, medium: 0, low: 0, pending: state.patients.length };
      state.ward_counts = Object.fromEntries(
        [...new Set(state.patients.map((patient) => patient.ward))]
          .sort()
          .map((ward) => [
            ward,
            {
              patients: state.patients.filter((patient) => patient.ward === ward).length,
              alerts: 0,
            },
          ])
      );
      state.patients = state.patients.map((patient) => ({
        ...patient,
        initial_risk_score: null,
        initial_risk_level: "pending",
        risk_score: null,
        risk_level: "pending",
        recommended_action: "Waiting for pipeline response",
        abnormal_vitals: [],
        alert: false,
        pipeline_comparison: {},
      }));
      render();
    }

    function criticalPatients() {
      return (state.patients || []).filter((patient) => patient.risk_level === "critical");
    }

    function showCriticalDialogForCurrentRun() {
      const patients = criticalPatients();
      if (!patients.length) return;
      const list = document.getElementById("criticalDialogList");
      list.innerHTML = patients.map((patient) => `
        <li>
          <strong>${patient.name}</strong> (${patient.patient_id}) -
          ${patient.ward} ${patient.bed} -
          score ${patient.risk_score ?? "n/a"} -
          ${patient.diagnosis}
        </li>
      `).join("");
      document.getElementById("criticalDialog").classList.add("open");
    }

    function closeCriticalDialog() {
      document.getElementById("criticalDialog").classList.remove("open");
    }

    function renderBenchmarkStatus() {
      const pill = document.getElementById("benchmarkStatus");
      const button = document.getElementById("runBenchmarkButton");
      const status = benchmarkState.status || "idle";
      pill.textContent = status;
      pill.className = `status-pill ${status}`;
      button.disabled = status === "running";
    }

    function startStatusPolling() {
      if (statusPoll) return;
      statusPoll = window.setInterval(loadBenchmarkStatus, 2500);
    }

    function stopStatusPolling() {
      if (!statusPoll) return;
      window.clearInterval(statusPoll);
      statusPoll = null;
    }

    async function loadBenchmarkStatus() {
      try {
        const previousStatus = benchmarkState.status;
        const response = await fetch("/api/benchmark/status", { cache: "no-store" });
        benchmarkState = await response.json();
        renderBenchmarkStatus();
        if (benchmarkState.running) {
          startStatusPolling();
          return;
        }
        stopStatusPolling();
        if (previousStatus === "running" && benchmarkState.status === "completed") {
          await loadData();
          showCriticalDialogForCurrentRun();
        }
      } catch (error) {
        benchmarkState = { status: "unavailable", running: false };
        renderBenchmarkStatus();
        stopStatusPolling();
      }
    }

    async function runBenchmark() {
      const button = document.getElementById("runBenchmarkButton");
      button.disabled = true;
      try {
        const response = await fetch("/api/benchmark/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        });
        if (response.status === 409) {
          await loadBenchmarkStatus();
          return;
        }
        if (!response.ok) {
          throw new Error(`Run failed: ${response.status}`);
        }
        benchmarkState = await response.json().catch(() => ({ status: "running", running: true }));
        renderBenchmarkStatus();
        resetDashboardForRun();
        startStatusPolling();
      } catch (error) {
        benchmarkState = { status: "failed", running: false };
        renderBenchmarkStatus();
      }
    }

    document.getElementById("wardFilter").addEventListener("change", render);
    document.getElementById("riskFilter").addEventListener("change", render);
    document.getElementById("searchBox").addEventListener("input", render);
    document.getElementById("refreshButton").addEventListener("click", loadData);
    document.getElementById("runBenchmarkButton").addEventListener("click", runBenchmark);
    document.getElementById("criticalDialogClose").addEventListener("click", closeCriticalDialog);
    document.getElementById("criticalDialog").addEventListener("click", (event) => {
      if (event.target.id === "criticalDialog") closeCriticalDialog();
    });
    loadData({ pending: true });
    loadBenchmarkStatus();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, log_level="info")
