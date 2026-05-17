import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "cloud-edge-pipeline-benchmark-report.pdf"
PATIENTS = json.loads((ROOT / "data" / "patients.json").read_text(encoding="utf-8"))


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


GCP_ENV = read_env_file(ROOT / ".env.gcp")
GCP_PROJECT_ID = GCP_ENV.get("GCP_PROJECT_ID", "benchmark-edge-cloud")
GCP_REGION = GCP_ENV.get("GCP_REGION", "europe-west8")
GCP_CLOUD_URL = GCP_ENV.get(
    "GCP_CLOUD_URL",
    "https://benchmark-cloud-api-x7byt6caoq-oc.a.run.app",
)


def code(text: str) -> str:
    return f"<font name='Courier'>{text}</font>"


def page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#526273"))
    canvas.drawString(16 * mm, 10 * mm, "Clinical Cloud vs Edge Pipeline Benchmark")
    canvas.drawRightString(A4[0] - 16 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def make_styles():
    styles = getSampleStyleSheet()
    styles["Title"].fontName = "Helvetica-Bold"
    styles["Title"].fontSize = 25
    styles["Title"].leading = 30
    styles["Title"].alignment = TA_CENTER
    styles["Title"].textColor = colors.HexColor("#0b253a")

    styles["Heading1"].fontName = "Helvetica-Bold"
    styles["Heading1"].fontSize = 15
    styles["Heading1"].leading = 19
    styles["Heading1"].spaceBefore = 14
    styles["Heading1"].spaceAfter = 8
    styles["Heading1"].textColor = colors.HexColor("#0b253a")

    styles["Heading2"].fontName = "Helvetica-Bold"
    styles["Heading2"].fontSize = 12
    styles["Heading2"].leading = 15
    styles["Heading2"].spaceBefore = 10
    styles["Heading2"].spaceAfter = 5
    styles["Heading2"].textColor = colors.HexColor("#0b253a")

    styles["BodyText"].fontName = "Helvetica"
    styles["BodyText"].fontSize = 9.4
    styles["BodyText"].leading = 12.6
    styles["BodyText"].spaceAfter = 6

    styles.add(
        ParagraphStyle(
            name="Subtitle",
            parent=styles["BodyText"],
            fontSize=12,
            leading=16,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#526273"),
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CodeBlock",
            parent=styles["Code"],
            fontName="Courier",
            fontSize=8,
            leading=10,
            borderColor=colors.HexColor("#d9e2ea"),
            borderWidth=0.6,
            borderPadding=7,
            backColor=colors.HexColor("#f4f7fa"),
            spaceBefore=4,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Callout",
            parent=styles["BodyText"],
            borderColor=colors.HexColor("#0f6b8f"),
            borderWidth=0.8,
            borderPadding=8,
            backColor=colors.HexColor("#eef7fb"),
            spaceBefore=6,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableHeader",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.6,
            leading=9.2,
            textColor=colors.HexColor("#0b253a"),
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableCell",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=7.3,
            leading=9.0,
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableCellSmall",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=6.8,
            leading=8.2,
            wordWrap="CJK",
        )
    )
    return styles


S = make_styles()


def p(text: str):
    return Paragraph(text, S["BodyText"])


def h1(text: str):
    return Paragraph(text, S["Heading1"])


def h2(text: str):
    return Paragraph(text, S["Heading2"])


def pre(text: str):
    return Preformatted(text.strip("\n"), S["CodeBlock"])


def bullets(items):
    return ListFlowable(
        [ListItem(Paragraph(item, S["BodyText"]), leftIndent=12) for item in items],
        bulletType="bullet",
        leftIndent=14,
        bulletFontSize=6,
    )


def numbered(items):
    return ListFlowable(
        [ListItem(Paragraph(item, S["BodyText"]), leftIndent=14) for item in items],
        bulletType="1",
        leftIndent=16,
    )


def table_cell(value, is_header: bool, small: bool):
    if isinstance(value, Paragraph):
        return value
    style = S["TableHeader"] if is_header else S["TableCellSmall" if small else "TableCell"]
    text = escape(str(value)).replace("\n", "<br/>")
    return Paragraph(text, style)


def table(data, widths, small: bool = False):
    wrapped = [
        [table_cell(cell, row_index == 0, small) for cell in row]
        for row_index, row in enumerate(data)
    ]
    tbl = Table(wrapped, colWidths=widths, repeatRows=1, hAlign="LEFT", splitByRow=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef4f8")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0b253a")),
                ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#d7dee7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return tbl


def dataset_summary_table():
    rows = [["Patient", "Ward / Bed", "Diagnosis", "Latest Vitals"]]
    for patient in PATIENTS:
        latest = patient["vitals"][-1]
        rows.append(
            [
                f"{patient['patient_id']}\n{patient['name']} ({patient['age']}{patient['sex']})",
                f"{patient['ward']}\n{patient['bed']}",
                patient["primary_diagnosis"],
                f"HR {latest['heart_rate']} | SBP {latest['systolic_bp']} | RR {latest['respiratory_rate']}\nSpO2 {latest['spo2']}% | T {latest['temperature']} | Glu {latest['glucose']}",
            ]
        )
    return table(rows, [34 * mm, 31 * mm, 50 * mm, 63 * mm], small=True)


def build_story():
    story = []
    story.append(Paragraph("Clinical Cloud vs Edge Pipeline Benchmark", S["Title"]))
    story.append(
        Paragraph(
            "Updated technical report for the current Google Cloud Run + local edge benchmark: wearable alert validation, edge HTTP/TLS comparison, pipeline logs, metrics, and hospital dashboard outputs.",
            S["Subtitle"],
        )
    )
    story.append(pre(f"""
Repository: cloud-edge-pipeline-benchmark
Dataset: data/patients.json
Google Cloud project: {GCP_PROJECT_ID}
Google Cloud region: {GCP_REGION}
Cloud Run service URL: {GCP_CLOUD_URL}
Dashboard: http://localhost:8080
Benchmark command: docker compose --env-file .env.gcp run --rm benchmark
Scenarios: cloud, edge, edge_tls
Default run size: 20 patients x 3 scenarios x 3 repeats = 180 requests
"""))

    story.append(h1("1. What This Benchmark Demonstrates"))
    story.append(
        p(
            "The project now compares three request/response paths for the same synthetic patient wearable sample. The cloud path sends the sample to Google Cloud Run over platform HTTPS. The edge HTTP path sends the same sample to a local ward gateway without TLS. The edge TLS path sends it to the same local gateway over HTTPS/TLS. All paths execute the same wearable validation and out-of-range alert logic, then return an alert payload to the runner and dashboard."
        )
    )
    story.append(
        p(
            "The measurement intentionally excludes an edge-to-cloud callback. The benchmark is therefore an end-to-end latency comparison between the dashboard or runner and each processing destination, not a study of asynchronous data replication."
        )
    )
    story.append(
        Paragraph(
            "<b>Important:</b> the patients are synthetic. They are realistic enough for benchmarking and dashboard design, but they are not real patients and must not be interpreted as medical advice.",
            S["Callout"],
        )
    )

    story.append(h1("2. Patient Dataset"))
    story.append(
        p(
            f"The benchmark uses {len(PATIENTS)} synthetic patient records. Each record contains demographics, location, diagnosis, comorbidities, medications, and three recent vital-sign samples."
        )
    )
    story.append(pre("""
patient_id, name, age, sex
ward, bed
primary_diagnosis
comorbidities[]
medications[]
vitals[]:
  timestamp
  heart_rate
  systolic_bp
  respiratory_rate
  spo2
  temperature
  glucose
"""))
    story.append(h2("Dataset snapshot"))
    story.append(dataset_summary_table())

    story.append(PageBreak())

    story.append(h1("3. Cloud Pipeline in Detail"))
    story.append(
        p(
            "The cloud pipeline is the only cloud execution path in the current stack. It receives the wearable sample at the public Google Cloud Run /process endpoint, validates the payload, checks the latest vital-sign sample against clinical thresholds, stores the full patient record for the cloud scenario, and returns the alert result to the caller."
        )
    )
    story.append(pre("""
dashboard / benchmark runner
  -> Google Cloud Run /process
  -> wearable payload validation
  -> out-of-range threshold checks
  -> alert generation
  -> cloud storage stage
  -> response to dashboard/runner
"""))
    story.append(h2("Information sent to Cloud Run"))
    story.append(
        bullets(
            [
                "Patient demographics and hospital location.",
                "Diagnosis, comorbidities, and medications.",
                "Wearable vital-sign series for heart rate, systolic blood pressure, respiratory rate, SpO2, temperature, and glucose.",
                "Benchmark metadata such as input_id, complexity, and security profile.",
            ]
        )
    )
    story.append(h2("Information returned by cloud"))
    story.append(
        bullets(
            [
                "Risk score and alert level: low, medium, high, or critical.",
                "Out-of-range vital findings with value, unit, normal range, and direction.",
                "Recommended clinical action.",
                "Timing fields for network, validation, threshold check, storage, and total service time.",
                "Process age for the service instance that handled the request.",
            ]
        )
    )

    story.append(h1("4. Edge Pipeline in Detail"))
    story.append(
        p(
            "The edge pipeline runs the same wearable alert validation locally in Docker. The edge is configured as a constrained ward gateway with 0.5 CPU, 256 MB memory, and a 128 process limit. The HTTP and TLS variants use identical application logic and resource limits so the benchmark can isolate local transport and request overhead."
        )
    )
    story.append(pre("""
dashboard / benchmark runner
  -> edge-api /process
  -> wearable payload validation
  -> out-of-range threshold checks
  -> local alert generation
  -> response to dashboard/runner
"""))
    story.append(h2("Information processed locally at the edge"))
    story.append(
        bullets(
            [
                "The same patient sample sent to Cloud Run.",
                "The latest wearable vital-sign sample.",
                "The configured normal ranges for each vital sign.",
                "A local alert summary with pseudonymized patient hash.",
            ]
        )
    )
    story.append(h2("Information produced by the edge"))
    story.append(pre("""
patient_id
patient_hash pseudonymized from patient_id
ward
bed
latest_vitals
risk_score
risk_level
abnormal_vitals
recommended_action
alert
"""))
    story.append(
        p(
            "During the measured edge scenarios, CLOUD_SYNC_URL is empty. Edge results are returned to the benchmark runner and dashboard only; payload_synced_kb and sync_ms remain zero unless an explicit sync endpoint is configured."
        )
    )
    story.append(
        p(
            "The edge service time is intentionally higher than the cloud service time. The local edge containers are configured as ward-gateway-0.5vcpu-256mb with PREPROCESS_MS=58 and INFERENCE_MS=110, while the Cloud Run deployment uses PREPROCESS_MS=24, INFERENCE_MS=36, and STORAGE_MS=12. This makes the edge path represent constrained hospital hardware rather than a full cloud runtime."
        )
    )

    story.append(h1("5. Google Cloud Run Deployment"))
    story.append(
        p(
            "The cloud API is deployed to Google Cloud Run. The compose stack no longer starts a local cloud API by default; it starts the local edge services, dashboard, Prometheus, Grafana, and benchmark runner while CLOUD_URL points to Cloud Run. In the current configuration, the Google Cloud project is "
            f"{code(GCP_PROJECT_ID)}, the selected European region is {code(GCP_REGION)}, and the deployed Cloud Run endpoint is {code(GCP_CLOUD_URL)}."
        )
    )
    story.append(pre(f"""
Google Cloud
  Artifact Registry: {GCP_REGION}-docker.pkg.dev/{GCP_PROJECT_ID}/benchmark/pipeline-api:latest
  Cloud Run service: benchmark-cloud-api
  Public HTTPS endpoint: {GCP_CLOUD_URL}
  Runtime role: cloud
  Transport security label: platform_tls
  Default min instances: 1

Local machine / hospital edge
  edge-api-local:     http://localhost:8001
  edge-api-tls-local: https://localhost:8444
  benchmark-control:  http://localhost:8090
  hospital-dashboard: http://localhost:8080
  prometheus:         http://localhost:9090
  grafana:            http://localhost:3000
"""))
    story.append(
        p(
            "The deployment script uses MinInstances=1 by default to keep the cloud service warm for a stable edge/cloud comparison. Passing MinInstances=0 or updating the service to --min-instances 0 enables separate Cloud Run cold-start experiments, but the application benchmark does not expose a cold-start counter because a local first-request flag would not represent real infrastructure startup."
        )
    )
    story.append(
        p(
            "Earlier versions exposed a cold_start_candidate value based on the first /process request observed by a Python process. That value was removed from the API response, benchmark CSV, dashboard summary, Prometheus metrics, and report because it only marked a local first request and could be mistaken for the real Cloud Run service startup time."
        )
    )
    story.append(h2("Execution path"))
    story.append(pre("""
benchmark-runner local
  -> HTTPS request to Google Cloud Run /process for cloud

benchmark-runner local
  -> HTTP request to edge-api /process for edge

benchmark-runner local
  -> HTTPS request to edge-api-tls /process for edge_tls

prometheus local
  -> scrapes local edge-api /metrics
  -> scrapes local edge-api-tls /metrics
  -> does not scrape Cloud Run by default
"""))
    story.append(
        bullets(
            [
                "The cloud path includes real internet routing from the local machine to Google Cloud Run.",
                "The edge paths keep validation and alert generation local and do not include cloud synchronization in measured latency.",
                "Prometheus avoids Cloud Run by default so it does not keep the cloud instance warm during latency experiments.",
                "An optional docker-compose.cloud-metrics.yml overlay enables Cloud Run /metrics scraping when cloud application metrics are desired.",
                "The hospital dashboard continues to read benchmark result files from the local results directory.",
            ]
        )
    )

    story.append(PageBreak())

    story.append(h1("6. Clinical Processing Logic"))
    story.append(p(f"The processing logic is implemented in {code('services/pipeline_api/app/clinical.py')}."))
    logic_rows = [
        ["Step", "Cloud", "Edge"],
        ["Schema validation", "Checks required patient fields and vital samples.", "Same validation before local processing."],
        ["Latest sample extraction", "Uses the latest wearable sample from the received series.", "Uses the same latest wearable sample."],
        ["Range normalization", "Clamps values to broad plausible sensor ranges before comparison.", "Same normalization."],
        ["Threshold check", "Compares HR, SBP, RR, SpO2, temperature, and glucose against configured normal ranges.", "Same threshold logic."],
        ["Alerting", "Returns low, medium, high, or critical with recommended action.", "Returns the same alert model locally."],
        ["Storage/sync", "Runs cloud storage stage and reports payload_synced_kb as the sent payload.", "No cloud sync during benchmark; payload_synced_kb is 0."],
    ]
    story.append(table(logic_rows, [32 * mm, 73 * mm, 73 * mm]))

    story.append(h2("Vital thresholds"))
    threshold_rows = [
        ["Vital", "Normal range", "Unit"],
        ["heart_rate", "50 - 110", "bpm"],
        ["systolic_bp", "90 - 160", "mmHg"],
        ["respiratory_rate", "10 - 24", "/min"],
        ["spo2", "94 - 100", "%"],
        ["temperature", "35.8 - 38.0", "C"],
        ["glucose", "70 - 180", "mg/dL"],
    ]
    story.append(table(threshold_rows, [54 * mm, 70 * mm, 54 * mm]))
    story.append(h2("Alert model"))
    story.append(
        bullets(
            [
                "Critical: SpO2 below 90.",
                "High: three or more out-of-range vital signs.",
                "Medium: at least one out-of-range vital sign.",
                "Low: no validation errors and no out-of-range vital signs.",
                "Any schema validation error also raises the alert flag.",
            ]
        )
    )

    story.append(h1("7. Executed Benchmark Pipelines"))
    story.append(pre("""
cloud
edge
edge_tls
"""))
    story.append(
        p(
            "The default BENCHMARK_SCENARIOS value is cloud,edge,edge_tls. The runner repeats the 20-patient dataset three times and sends the three scenario requests for each patient concurrently, producing 180 rows in results.csv."
        )
    )
    scenario_rows = [
        ["Scenario", "Processing", "Transport", "Purpose"],
        ["cloud", "Cloud Run wearable validation", "Google platform HTTPS", "Measures client-to-Cloud-Run round trip plus service processing."],
        ["edge", "Local wearable validation", "HTTP", "Measures constrained local ward-gateway processing without TLS."],
        ["edge_tls", "Local wearable validation", "HTTPS/TLS", "Measures the same local edge application over TLS."],
    ]
    story.append(table(scenario_rows, [34 * mm, 52 * mm, 42 * mm, 50 * mm], small=True))
    story.append(h2("Latency interpretation"))
    story.append(
        bullets(
            [
                "Mean round trip is measured by the benchmark client and includes transport, HTTP/TLS overhead, service execution, and scheduling effects.",
                "Mean service in the dashboard is computed from the internal processing stages: preprocess, inference, storage, and sync.",
                "The edge and edge_tls service means are expected to be close to each other because real TLS overhead is mostly outside the internal service-stage sum.",
                "The dashboard no longer shows cold starts. Real Cloud Run cold-start analysis should be handled as a separate infrastructure experiment with min-instances=0 and Cloud Monitoring or controlled request timing.",
            ]
        )
    )

    story.append(PageBreak())

    story.append(h1("8. Benchmark Outputs"))
    story.append(pre("""
results/results.csv
results/summary.json
results/patient_results.json
"""))
    story.append(
        p(
            f"{code('results.csv')} is the technical benchmark table. {code('summary.json')} aggregates latency, payload, and alert counts by scenario. {code('patient_results.json')} is optimized for the hospital dashboard."
        )
    )
    csv_rows = [
        ["Field", "Meaning"],
        ["repeat", "Dataset repeat index. Default repeats are 1, 2, and 3."],
        ["patient_id, ward, bed, diagnosis", "Clinical context of the processed patient."],
        ["client_total_ms", "End-to-end latency seen by the benchmark client."],
        ["service_total_ms", "Time measured inside the API handler."],
        ["client_service_delta_ms", "Client-side overhead not measured inside the service. TLS handshake and HTTP overhead mainly appear here."],
        ["transport_security", "plain, tls, or platform_tls."],
        ["process_age_ms", "Age of the service process when it handled the request."],
        ["network_ms", "Configured network delay stage."],
        ["preprocess_ms", "Wearable payload validation stage."],
        ["inference_ms", "Out-of-range threshold check and alert generation stage."],
        ["sync_ms", "Cloud synchronization time. It is 0 for edge scenarios in the direct comparison."],
        ["payload_sent_kb", "Input payload sent by the benchmark client."],
        ["payload_synced_kb", "Payload stored or synchronized to cloud. Cloud reports the sent payload; edge reports 0 with sync disabled."],
        ["abnormal_vitals_count, abnormal_vitals", "Number and details of out-of-range vital signs."],
        ["risk_score, risk_level", "Computed patient risk."],
        ["recommended_action", "Operational recommendation for the ward team."],
    ]
    story.append(table(csv_rows, [43 * mm, 135 * mm]))

    story.append(h1("9. Hospital Dashboard"))
    story.append(p(f"The hospital dashboard is served by {code('services/hospital_dashboard/app/main.py')} at {code('http://localhost:8080')}."))
    story.append(
        bullets(
            [
                "Patient worklist sorted by risk.",
                "Ward and risk filters.",
                "Latest vital signs for the selected patient.",
                "Diagnosis, medications, comorbidities, risk score, out-of-range values, and recommended action.",
                "Per-patient comparison of cloud, edge, and edge_tls latency, service time, transport, payload, and risk result.",
                "Latency table with runs, mean round trip, p99 round trip, and mean service for each scenario.",
                "No cold-start column: the previous local first-request marker was removed because it did not measure true infrastructure startup.",
                "Ward load and active alert count.",
                "Critical-patient dialog after a benchmark run when critical results are present.",
            ]
        )
    )
    story.append(
        p(
            "The dashboard reads patient_results.json after the benchmark runs. If the benchmark has not been executed yet, it still displays the dataset and marks patients as pending."
        )
    )

    story.append(h1("10. Prometheus and Grafana"))
    story.append(
        p(
            "Prometheus collects runtime metrics from the API services. It does not execute the benchmark. Grafana visualizes those metrics over time. The hospital dashboard is separate: it visualizes clinical benchmark results."
        )
    )
    story.append(pre("""
pipeline_requests_total
pipeline_total_latency_ms
pipeline_stage_latency_ms
pipeline_payload_size_kb
pipeline_in_flight_requests
pipeline_process_started_at_seconds
"""))
    story.append(
        p(
            "The default Prometheus configuration scrapes only the local edge services. This avoids accidental Cloud Run warm-up before latency tests. If cloud application metrics are needed, configure-gcp-hybrid.ps1 also generates prometheus.gcp.with-cloud.yml and docker-compose.cloud-metrics.yml can mount it."
        )
    )
    story.append(h2("Structured pipeline logs"))
    story.append(
        p(
            "Both Cloud Run and local edge services emit JSON log events named clinical_pipeline_step. They include pseudonymized patient hash, ward, bed, diagnosis, vital-sample count, clinical fields used, timing, risk result, abnormal vital details, and process age. Patient names and raw vital values are not logged in the step context."
        )
    )
    story.append(pre("""
request_received
network_uplink
transport_security
wearable_payload_validation
abnormal_threshold_check
cloud_storage
dashboard_response
"""))

    story.append(h1("11. Commands"))
    story.append(pre("""
powershell -ExecutionPolicy Bypass -File scripts\\deploy-cloud-run.ps1 `
  -ProjectId benchmark-edge-cloud `
  -Region europe-west8

start_benchmark.bat

docker compose --env-file .env.gcp up --build

docker compose --env-file .env.gcp run --rm benchmark

powershell -ExecutionPolicy Bypass -File scripts\\deploy-cloud-run.ps1 `
  -ProjectId benchmark-edge-cloud `
  -Region europe-west8 `
  -MinInstances 0

docker compose ps
docker compose logs -f edge-api edge-api-tls benchmark-api hospital-dashboard
docker compose down
"""))

    story.append(h1("12. Limitations"))
    story.append(
        bullets(
            [
                "The dataset is synthetic and small by design.",
                "The alert model is deterministic and threshold-based; it is not a validated medical device or clinical decision support model.",
                "The edge is emulated through Docker CPU/RAM limits, not real bedside hardware.",
                "The edge TLS certificate is local and self-signed for benchmarking, not production use.",
                "Cloud Run HTTPS is real but terminated by the Google Cloud platform rather than the application container.",
                "The benchmark no longer reports cold starts because a process-local first-request marker would be a misleading proxy for real service startup.",
                "Real Cloud Run cold-start experiments require separate control of min-instances, warm-up traffic, monitoring scrapes, and request timing.",
                "The cloud benchmark depends on the local network path from the workstation to Google Cloud Europe.",
                "Network delay is simulated at application level; a stronger network study could use tc netem, Mininet, or Containernet.",
            ]
        )
    )

    return story


def main():
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Clinical Cloud vs Edge Pipeline Benchmark",
        author="Codex",
    )
    doc.build(build_story(), onFirstPage=page_number, onLaterPages=page_number)
    print(OUTPUT)


if __name__ == "__main__":
    main()
