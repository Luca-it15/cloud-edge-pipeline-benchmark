from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    ListFlowable,
    ListItem,
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


def code(text: str) -> str:
    return f"<font name='Courier'>{text}</font>"


def page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#526273"))
    canvas.drawString(16 * mm, 10 * mm, "Cloud vs Edge Pipeline Benchmark")
    canvas.drawRightString(A4[0] - 16 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def styles():
    base = getSampleStyleSheet()
    base["Title"].fontName = "Helvetica-Bold"
    base["Title"].fontSize = 26
    base["Title"].leading = 31
    base["Title"].textColor = colors.HexColor("#0b253a")
    base["Title"].alignment = TA_CENTER

    base["Heading1"].fontName = "Helvetica-Bold"
    base["Heading1"].fontSize = 16
    base["Heading1"].leading = 20
    base["Heading1"].spaceBefore = 14
    base["Heading1"].spaceAfter = 8
    base["Heading1"].textColor = colors.HexColor("#0b253a")

    base["Heading2"].fontName = "Helvetica-Bold"
    base["Heading2"].fontSize = 12
    base["Heading2"].leading = 15
    base["Heading2"].spaceBefore = 10
    base["Heading2"].spaceAfter = 5
    base["Heading2"].textColor = colors.HexColor("#0b253a")

    base["BodyText"].fontName = "Helvetica"
    base["BodyText"].fontSize = 9.5
    base["BodyText"].leading = 13
    base["BodyText"].spaceAfter = 6
    base["BodyText"].textColor = colors.HexColor("#16202a")

    base.add(
        ParagraphStyle(
            name="Subtitle",
            parent=base["BodyText"],
            fontSize=12,
            leading=16,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#526273"),
            spaceAfter=12,
        )
    )
    base.add(
        ParagraphStyle(
            name="CodeBlock",
            parent=base["Code"],
            fontName="Courier",
            fontSize=8,
            leading=10,
            leftIndent=0,
            rightIndent=0,
            borderColor=colors.HexColor("#d9e2ea"),
            borderWidth=0.7,
            borderPadding=7,
            backColor=colors.HexColor("#f4f7fa"),
            spaceBefore=4,
            spaceAfter=8,
        )
    )
    base.add(
        ParagraphStyle(
            name="Callout",
            parent=base["BodyText"],
            leftIndent=8,
            rightIndent=8,
            borderColor=colors.HexColor("#146c94"),
            borderWidth=0.8,
            borderPadding=7,
            backColor=colors.HexColor("#eef7fb"),
            spaceBefore=6,
            spaceAfter=8,
        )
    )
    return base


S = styles()


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
        start="circle",
        leftIndent=14,
        bulletFontSize=6,
    )


def numbered(items):
    return ListFlowable(
        [ListItem(Paragraph(item, S["BodyText"]), leftIndent=14) for item in items],
        bulletType="1",
        leftIndent=16,
    )


def table(data, widths=None):
    tbl = Table(data, colWidths=widths, hAlign="LEFT", repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef4f8")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0b253a")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("LEADING", (0, 0), (-1, -1), 10.5),
                ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#d7dee7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return tbl


def build_story():
    story = []
    story.append(Paragraph("Cloud vs Edge Pipeline Benchmark", S["Title"]))
    story.append(
        Paragraph(
            "Technical explanation of the Docker Compose benchmark, real TLS/mTLS communication, simulated security overhead, Prometheus metrics, and Grafana visualization.",
            S["Subtitle"],
        )
    )
    story.append(pre("Project: cloud-edge-pipeline-benchmark\nStart: docker compose up --build\nRun benchmark: docker compose run --rm benchmark"))

    story.append(h1("1. Purpose of the Project"))
    story.append(
        p(
            "This project is a local, reproducible benchmark environment for comparing cloud and edge processing pipelines. It shows how latency, synchronization cost, logical bandwidth usage, and security overhead change when the same workload is executed in different deployment models."
        )
    )
    story.append(
        Paragraph(
            "<b>Core comparison:</b> in the cloud pipeline, raw data is sent to the cloud and processed there. In the edge pipeline, data is processed near the source and only a reduced result is synchronized to the cloud.",
            S["Callout"],
        )
    )

    story.append(h1("2. High-Level Architecture"))
    story.append(
        p(
            "Docker Compose starts multiple services on a shared Docker network. Plain HTTP services and TLS/mTLS services are kept separate so their performance can be compared directly."
        )
    )
    story.append(pre("""
Plain cloud pipeline
Client -> cloud-api HTTP -> simulated network -> preprocessing -> inference -> storage

Plain edge pipeline
Client -> edge-api HTTP -> simulated local network -> preprocessing -> inference -> sync reduced result to cloud

TLS edge pipeline
Client -> HTTPS/mTLS -> edge-api-tls -> preprocessing -> inference -> HTTPS/mTLS sync to cloud-api-tls
"""))

    story.append(h1("3. Docker Compose Services"))
    service_data = [
        ["Service", "Role", "Port"],
        [code("certgen"), "Generates local CA, server certificates, and client certificate for TLS/mTLS.", "N/A"],
        [code("cloud-api"), "Plain HTTP cloud processing service.", "8000"],
        [code("edge-api"), "Plain HTTP edge processing service with CPU/RAM limits.", "8001"],
        [code("cloud-api-tls"), "HTTPS/mTLS cloud processing service.", "8443"],
        [code("edge-api-tls"), "HTTPS/mTLS edge service that syncs results to cloud-api-tls.", "8444"],
        [code("benchmark"), "Batch runner that calls every scenario and writes CSV/JSON output.", "N/A"],
        [code("prometheus"), "Scrapes runtime metrics from the API services.", "9090"],
        [code("grafana"), "Visualizes Prometheus metrics through a provisioned dashboard.", "3000"],
    ]
    story.append(table(service_data, [38 * mm, 100 * mm, 25 * mm]))

    story.append(h1("4. How Startup Works"))
    story.append(pre("docker compose up --build"))
    story.append(
        numbered(
            [
                "Builds the Python images for the API, benchmark runner, and certificate generator.",
                f"Runs {code('certgen')}, which writes certificates into {code('certs/')}.",
                "Starts the plain HTTP cloud and edge APIs.",
                "Starts the HTTPS/mTLS cloud and edge APIs after certificates exist.",
                "Starts Prometheus and configures it to scrape both HTTP and HTTPS/mTLS endpoints.",
                "Starts Grafana and provisions the Prometheus data source plus the dashboard.",
            ]
        )
    )
    story.append(pre("""
Cloud API plain:      http://localhost:8000/docs
Edge API plain:       http://localhost:8001/docs
Cloud API TLS/mTLS:   https://localhost:8443/docs
Edge API TLS/mTLS:    https://localhost:8444/docs
Prometheus:           http://localhost:9090
Grafana:              http://localhost:3000
"""))
    story.append(
        Paragraph(
            "<b>Note:</b> the TLS endpoints use a local self-signed CA and require a client certificate. The benchmark and Prometheus are configured automatically. A browser may reject the TLS pages unless the local CA and client certificate are imported.",
            S["Callout"],
        )
    )

    story.append(PageBreak())

    story.append(h1("5. API Behavior"))
    story.append(
        p(
            f"The API service is implemented with FastAPI in {code('services/pipeline_api/app/main.py')}. The same image is reused for cloud and edge; behavior changes through environment variables such as {code('ROLE')}, {code('NETWORK_UPLINK_MS')}, {code('PREPROCESS_MS')}, and {code('INFERENCE_MS')}."
        )
    )
    story.append(pre("""
POST /process

{
  "input_id": "sample-001",
  "data_size_kb": 512,
  "complexity": 1.0,
  "security_profile": "none | simulated | tls"
}
"""))
    story.append(h2("Cloud mode"))
    story.append(
        numbered(
            [
                "Apply simulated network uplink delay.",
                "Optionally apply simulated security stages.",
                "Run synthetic preprocessing.",
                "Run synthetic inference.",
                "Run simulated storage.",
                "Return timing data to the client.",
            ]
        )
    )
    story.append(h2("Edge mode"))
    story.append(
        numbered(
            [
                "Apply smaller simulated local network delay.",
                "Optionally apply simulated security stages.",
                "Run synthetic preprocessing on the constrained edge container.",
                "Run synthetic inference on the constrained edge container.",
                f"Send a reduced result to the cloud through {code('/sync')}.",
                "Return timing data to the client.",
            ]
        )
    )

    story.append(h1("6. Benchmark Scenarios"))
    story.append(p(f"The benchmark runner is implemented in {code('services/benchmark/benchmark.py')}. Run it with:"))
    story.append(pre("docker compose run --rm benchmark"))
    scenario_data = [
        ["Scenario", "Meaning", "Transport"],
        [code("cloud"), "Raw data is sent to cloud and processed there.", "HTTP"],
        [code("edge"), "Data is processed at the edge; a reduced result is synced to cloud.", "HTTP"],
        [code("cloud_simulated_secure"), "Cloud pipeline with configurable simulated security overhead.", "HTTP"],
        [code("edge_simulated_secure"), "Edge pipeline with configurable simulated security overhead.", "HTTP"],
        [code("cloud_tls"), "Cloud pipeline over real HTTPS/mTLS.", "HTTPS/mTLS"],
        [code("edge_tls"), "Edge pipeline over real HTTPS/mTLS, including TLS sync to cloud.", "HTTPS/mTLS"],
    ]
    story.append(table(scenario_data, [48 * mm, 88 * mm, 28 * mm]))
    story.append(pre("RUNS: 30\nDATA_SIZE_KB: 512\nCOMPLEXITY: 1.0"))

    story.append(h1("7. Security Model"))
    story.append(h2("Simulated security"))
    story.append(
        p(
            f"The {code('*_simulated_secure')} scenarios add explicit synthetic stages inside the API timer. This is useful for explaining the theoretical performance cost of communication security mechanisms."
        )
    )
    story.append(
        bullets(
            [
                f"{code('security_tls_handshake')}: simulated TLS or mTLS handshake cost.",
                f"{code('security_hmac_auth')}: simulated token/HMAC verification cost.",
                f"{code('security_encrypt_decrypt')}: simulated payload encryption/decryption cost, proportional to payload size.",
                f"{code('security_replay_check')}: simulated nonce/timestamp replay-protection cost.",
            ]
        )
    )
    story.append(h2("Real TLS/mTLS"))
    story.append(
        p(
            f"The {code('*_tls')} scenarios use real HTTPS. Uvicorn is started with SSL settings, and each TLS service uses a certificate generated by {code('certgen')}. The benchmark client verifies the local CA and presents a client certificate. This models mutual TLS: the client validates the server, and the server requires a trusted client certificate."
        )
    )
    story.append(
        p(
            f"Real TLS overhead is not recorded as {code('security_ms')}, because it happens before the request reaches the FastAPI handler. It appears mainly in {code('client_service_delta_ms')}, the difference between client-observed end-to-end time and API-internal processing time."
        )
    )

    story.append(PageBreak())

    story.append(h1("8. Output Files and Interpretation"))
    story.append(pre("results/results.csv\nresults/summary.json"))
    csv_data = [
        ["Column", "Meaning"],
        [code("pipeline"), "Scenario name, such as cloud, edge_tls, or cloud_simulated_secure."],
        [code("client_total_ms"), "Total latency measured by the benchmark client."],
        [code("service_total_ms"), "Latency measured inside the API service."],
        [code("client_service_delta_ms"), "Client minus service timing. For TLS, includes handshake, certificate verification, connection setup, HTTP overhead, and serialization."],
        [code("security_ms"), "Simulated security overhead. Non-zero only in simulated secure scenarios."],
        [code("network_ms"), "Configured synthetic network delay."],
        [code("preprocess_ms"), "Measured synthetic preprocessing time."],
        [code("inference_ms"), "Measured synthetic inference time."],
        [code("sync_ms"), "For edge pipelines, time spent synchronizing the reduced result to cloud."],
        [code("payload_sent_kb"), "Logical input payload size sent by the client."],
        [code("payload_synced_kb"), "Logical payload sent to cloud. Raw input for cloud, reduced result for edge."],
    ]
    story.append(table(csv_data, [48 * mm, 115 * mm]))

    story.append(h1("9. Prometheus and Grafana"))
    story.append(
        p(
            "Prometheus does not run the benchmark. It periodically scrapes metrics exposed by each API service at /metrics. Grafana uses Prometheus as a data source to visualize these metrics."
        )
    )
    story.append(pre("""
API services expose:
  pipeline_requests_total
  pipeline_total_latency_ms
  pipeline_stage_latency_ms
  pipeline_payload_size_kb
  pipeline_in_flight_requests

Prometheus scrapes:
  http://cloud-api:8000/metrics
  http://edge-api:8000/metrics
  https://cloud-api-tls:8443/metrics
  https://edge-api-tls:8443/metrics
"""))
    story.append(
        p(
            "For TLS targets, Prometheus is configured with the local CA and client certificate. Monitoring itself is therefore performed over authenticated TLS."
        )
    )

    story.append(h1("10. Reading Typical Results"))
    story.append(
        bullets(
            [
                "The cloud pipeline often has lower compute time because the simulated cloud service has faster preprocessing and inference parameters.",
                "The edge pipeline has higher local compute time because the edge container is constrained with cpus: \"1.0\" and mem_limit: 512m.",
                "The edge advantage is lower logical cloud bandwidth: it synchronizes only the reduced result instead of the raw input.",
                f"The simulated secure scenarios show a configurable overhead in {code('security_ms')}.",
                f"The real TLS scenarios show transport overhead mainly through {code('client_service_delta_ms')} and, for edge, through higher {code('sync_ms')} because edge-to-cloud sync also uses HTTPS/mTLS.",
            ]
        )
    )

    story.append(h1("11. Useful Commands"))
    story.append(pre("""
# Start everything and build images
docker compose up --build

# Start in the background
docker compose up -d --build

# Run the benchmark once
docker compose run --rm benchmark

# Check service status
docker compose ps

# Watch API logs
docker compose logs -f cloud-api edge-api cloud-api-tls edge-api-tls

# Stop everything
docker compose down

# Regenerate certificates
docker compose run --rm -e FORCE_REGENERATE_CERTS=1 certgen
docker compose up -d --build
"""))

    story.append(h1("12. Limitations and Extensions"))
    story.append(
        p(
            "This environment is useful for controlled benchmarking and explanation, but it is still an emulation. It does not fully model thermal throttling, real sensor I/O, wireless interference, GPU/NPU acceleration, or production-grade certificate lifecycle management."
        )
    )
    story.append(
        bullets(
            [
                "Replace synthetic preprocessing/inference with a real ML model.",
                "Run the edge API on a Raspberry Pi, Jetson, or other real edge device.",
                "Add network emulation with tc netem or Containernet.",
                "Add concurrent users or streams to stress throughput and queueing behavior.",
                "Add real authentication tokens, signed payloads, and nonce persistence.",
                "Export Grafana panels for inclusion in a thesis or report.",
            ]
        )
    )

    story.append(h1("13. Repository Notes"))
    story.append(p("Generated certificates, private keys, and local benchmark outputs are intentionally ignored by Git:"))
    story.append(pre("certs/*.crt\ncerts/*.key\nresults/*.csv\nresults/*.json"))
    story.append(
        p(
            "This prevents accidental publication of private key material or machine-specific benchmark artifacts. The certificates can always be regenerated through the certgen service."
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
        title="Cloud vs Edge Pipeline Benchmark - Technical Report",
        author="Codex",
    )
    doc.build(build_story(), onFirstPage=page_number, onLaterPages=page_number)
    print(OUTPUT)


if __name__ == "__main__":
    main()
