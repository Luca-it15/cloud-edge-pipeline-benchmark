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
            "Detailed explanation of the patient dataset, local edge pipeline, Google Cloud Run deployment, transmitted information, security modes, executed benchmark pipelines, metrics, and hospital dashboard.",
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
Local benchmark: docker compose run --rm benchmark
Hybrid GCP benchmark: see Section 11 commands
"""))

    story.append(h1("1. What This Benchmark Demonstrates"))
    story.append(
        p(
            "The project compares two ways of processing hospital monitoring data. The cloud pipeline sends the complete patient record to a centralized API and performs every clinical processing step there. The edge pipeline processes the same record near the ward or bedside and creates a local early-warning alert. Cloud synchronization is not included in the measured edge latency, so the benchmark is a direct edge vs cloud comparison. The project also supports a hybrid benchmark where the cloud API is deployed on Google Cloud Run in Europe while the edge service and benchmark runner stay local."
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
            "The cloud pipeline represents a centralized architecture. The complete record is transmitted to the cloud API. This maximizes central visibility but also sends the largest amount of clinical information over the network."
        )
    )
    story.append(pre("""
benchmark client
  -> cloud-api /process
  -> simulated network delay
  -> schema validation
  -> vital-sign normalization and range clamping
  -> feature extraction on the full time series
  -> vital-sign score
  -> trend score
  -> clinical context score
  -> risk classification and triage recommendation
  -> full-record storage
  -> response to client
"""))
    story.append(h2("Information sent to cloud"))
    story.append(
        bullets(
            [
                "Full demographics: patient identifier, name, age, sex.",
                "Hospital context: ward and bed.",
                "Clinical context: diagnosis, comorbidities, medications.",
                "Complete vital-sign time series: heart rate, systolic blood pressure, respiratory rate, oxygen saturation, temperature, glucose.",
            ]
        )
    )
    story.append(h2("Information stored by cloud"))
    story.append(
        bullets(
            [
                "The full patient record.",
                "The complete vital-sign time series.",
                "Extracted features: latest values, averages, trends.",
                "Risk score, risk level, component scores, alert flag, and recommended action.",
            ]
        )
    )

    story.append(h1("4. Edge Pipeline in Detail"))
    story.append(
        p(
            "The edge pipeline represents processing close to the source. The edge receives the same raw record and performs early-warning logic locally. In this benchmark, cloud synchronization is disabled for edge scenarios, so the latency reflects the local edge pipeline only."
        )
    )
    story.append(pre("""
benchmark client
  -> edge-api /process
  -> simulated local network delay
  -> schema validation
  -> vital-sign range clamping
  -> moving-average noise filter
  -> local feature extraction
  -> early-warning score
  -> local alert generation
  -> response to client
"""))
    story.append(h2("Information processed locally at the edge"))
    story.append(
        bullets(
            [
                "The complete patient record.",
                "The complete vital-sign time series.",
                "Filtered vital-sign samples.",
                "Local clinical features and risk score.",
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
recommended_action
alert
"""))
    story.append(
        p(
            "In the direct comparison, this reduced payload is returned to the benchmark client but is not synchronized to the cloud. Therefore, edge scenarios report payload_synced_kb as 0 and sync_ms as 0."
        )
    )

    story.append(h1("5. Google Cloud Run Deployment"))
    story.append(
        p(
            "To make the benchmark closer to a real deployment, the cloud API container can be deployed on Google Cloud Run. In the current setup, the Google Cloud project is "
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

Local machine / simulated hospital edge
  edge-api
  benchmark-runner
  prometheus
  grafana
  hospital-dashboard
"""))
    story.append(
        p(
            "Cloud Run terminates public HTTPS at the Google-managed platform boundary. For this reason, the hybrid Google Cloud Run scenarios are labelled "
            f"{code('platform_tls')} rather than container-terminated mTLS. The local {code('cloud_tls')} and {code('edge_tls')} scenarios still use the repository's local mTLS certificates and remain useful for measuring container-level TLS overhead."
        )
    )
    story.append(h2("Hybrid Google Cloud execution path"))
    story.append(pre("""
benchmark-runner local
  -> HTTPS request to Google Cloud Run /process for cloud scenarios

benchmark-runner local
  -> local edge-api /process for edge scenarios

prometheus local
  -> scrapes local edge-api /metrics
  -> scrapes Google Cloud Run /metrics over HTTPS
"""))
    story.append(
        bullets(
            [
                "The cloud path includes real internet routing from the local machine to Google Cloud Run.",
                "The edge path keeps clinical preprocessing and risk scoring local and does not include cloud synchronization in the measured latency.",
                "Prometheus observes both local edge metrics and remote cloud metrics, while Grafana visualizes the collected time series.",
                "The hospital dashboard continues to read benchmark result files from the local results directory.",
            ]
        )
    )

    story.append(PageBreak())

    story.append(h1("6. Clinical Processing Logic"))
    story.append(p(f"The processing logic is implemented in {code('services/pipeline_api/app/clinical.py')}."))
    logic_rows = [
        ["Step", "Cloud", "Edge"],
        ["Validation", "Checks required fields and vital samples.", "Same validation before local processing."],
        ["Cleaning", "Clamps vital signs to plausible ranges.", "Clamps vital signs to plausible ranges."],
        ["Noise filtering", "Uses the raw time series for full central analysis.", "Applies moving-average smoothing before scoring."],
        ["Feature extraction", "Computes latest values, averages, and trends from the full time series.", "Computes latest values, averages, and trends from filtered vitals."],
        ["Risk scoring", "Vital score + trend score + clinical context score.", "Same scoring logic on filtered local features."],
        ["Alerting", "Cloud triage alert after central processing.", "Immediate local alert before cloud synchronization."],
        ["Storage/sync", "Stores full clinical payload.", "No cloud sync in the measured edge pipeline."],
    ]
    story.append(table(logic_rows, [32 * mm, 73 * mm, 73 * mm]))

    story.append(h2("Risk score components"))
    story.append(
        bullets(
            [
                "Vital score: heart rate, systolic pressure, respiratory rate, SpO2, temperature, glucose.",
                "Trend score: worsening heart rate, respiratory rate, SpO2, systolic pressure, and temperature across the samples.",
                "Context score: age, number of comorbidities, and high-risk diagnosis terms such as sepsis, pneumonia, COPD, heart failure, or stroke.",
                "Risk level: low, medium, high, or critical.",
            ]
        )
    )

    story.append(h1("7. Executed Benchmark Pipelines"))
    story.append(pre("""
cloud
edge
cloud_simulated_secure
edge_simulated_secure
cloud_tls
edge_tls
"""))
    story.append(
        p(
            "The benchmark compares the user-facing /process pipeline for cloud and edge. Edge scenarios do not call the cloud /sync endpoint during measurement, so the comparison is direct."
        )
    )
    story.append(h2("Local Docker benchmark scenarios"))
    local_scenario_rows = [
        ["Scenario", "Processing", "Transport", "Purpose"],
        ["cloud", "Full central processing", "HTTP", "Baseline centralized pipeline."],
        ["edge", "Local scoring", "HTTP", "Baseline edge pipeline without cloud sync."],
        ["cloud_simulated_secure", "Full central processing", "HTTP + simulated security stages", "Explain theoretical security overhead."],
        ["edge_simulated_secure", "Local scoring", "HTTP + simulated security stages", "Explain edge-side security overhead."],
        ["cloud_tls", "Full central processing", "HTTPS/mTLS", "Measure real transport security overhead."],
        ["edge_tls", "Local scoring", "HTTPS/mTLS", "Measure TLS on the client-edge request."],
    ]
    story.append(table(local_scenario_rows, [34 * mm, 49 * mm, 43 * mm, 52 * mm], small=True))

    gcp_scenario_rows = [
        ["Scenario", "Cloud target", "Edge target", "What is measured"],
        ["cloud", "Google Cloud Run /process", "Not used", "Real client-to-Google-Cloud latency plus cloud processing."],
        ["edge", "Not used", "Local edge-api /process", "Local edge processing without cloud synchronization."],
        ["cloud_simulated_secure", "Google Cloud Run /process", "Not used", "Google Cloud path plus simulated auth/crypto/replay costs."],
        ["edge_simulated_secure", "Not used", "Local edge-api /process", "Local edge path plus simulated security costs."],
    ]
    story.append(
        KeepTogether(
            [
                h2("Hybrid Google Cloud Run scenarios"),
                table(gcp_scenario_rows, [35 * mm, 45 * mm, 38 * mm, 60 * mm], small=True),
            ]
        )
    )

    story.append(
        p(
            f"In hybrid mode, {code('BENCHMARK_SCENARIOS')} is set to {code('cloud,edge,cloud_simulated_secure,edge_simulated_secure')} because Cloud Run provides platform HTTPS but does not terminate the repository's local mTLS certificates inside the container. The local TLS scenarios remain available in the standard Docker Compose benchmark."
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
        ["patient_id, ward, bed, diagnosis", "Clinical context of the processed patient."],
        ["client_total_ms", "End-to-end latency seen by the benchmark client."],
        ["service_total_ms", "Time measured inside the API handler."],
        ["client_service_delta_ms", "Client-side overhead not measured inside the service. TLS handshake and HTTP overhead mainly appear here."],
        ["network_ms", "Configured network delay stage."],
        ["preprocess_ms", "Validation, cleaning, filtering, and feature preparation stage."],
        ["inference_ms", "Clinical risk scoring stage."],
        ["sync_ms", "Cloud synchronization time. It is 0 for edge scenarios in the direct comparison."],
        ["payload_sent_kb", "Input payload sent by the benchmark client."],
        ["payload_synced_kb", "Payload sent to cloud. Full record in cloud mode, 0 in edge mode."],
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
                "Diagnosis, medications, comorbidities, risk score, and recommended action.",
                "Per-patient comparison of cloud, edge, simulated security, TLS, and Google Cloud hybrid scenarios when the corresponding benchmark run has been executed.",
                "Ward load and active alert count.",
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
"""))
    story.append(
        p(
            "In the local benchmark, Prometheus scrapes Docker service names such as cloud-api, edge-api, cloud-api-tls, and edge-api-tls. In the Google Cloud hybrid benchmark, Prometheus uses prometheus.gcp.yml to scrape the local edge-api and the Cloud Run HTTPS host generated in .env.gcp."
        )
    )

    story.append(h1("11. Commands"))
    story.append(pre("""
docker compose up --build
docker compose run --rm benchmark

powershell -ExecutionPolicy Bypass -File scripts\\deploy-cloud-run.ps1 `
  -ProjectId benchmark-edge-cloud `
  -Region europe-west8

docker compose --env-file .env.gcp `
  -f docker-compose.yml `
  -f docker-compose.gcp.yml up --build

docker compose --env-file .env.gcp `
  -f docker-compose.yml `
  -f docker-compose.gcp.yml run --rm benchmark

docker compose ps
docker compose logs -f cloud-api edge-api cloud-api-tls `
  edge-api-tls hospital-dashboard
docker compose down
"""))

    story.append(h1("12. Limitations"))
    story.append(
        bullets(
            [
                "The dataset is synthetic and small by design.",
                "The scoring model is deterministic and explanatory; it is not a validated medical model.",
                "The edge is emulated through Docker CPU/RAM limits, not real bedside hardware.",
                "TLS certificates are local self-signed certificates for benchmarking, not production certificates.",
                "Cloud Run platform HTTPS is real, but it is terminated by Google Cloud rather than by the application container.",
                "The hybrid Google Cloud benchmark depends on the local network path from the workstation to Google Cloud Europe.",
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
