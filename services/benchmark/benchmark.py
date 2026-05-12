import asyncio
import csv
import json
import os
import statistics
import ssl
import time
from pathlib import Path
from typing import Any

import httpx


CLOUD_URL = os.getenv("CLOUD_URL", "http://cloud-api:8000/process")
EDGE_URL = os.getenv("EDGE_URL", "http://edge-api:8000/process")
CLOUD_TLS_URL = os.getenv("CLOUD_TLS_URL", "https://cloud-api-tls:8443/process")
EDGE_TLS_URL = os.getenv("EDGE_TLS_URL", "https://edge-api-tls:8443/process")
TLS_CA_FILE = os.getenv("TLS_CA_FILE", "")
TLS_CLIENT_CERT_FILE = os.getenv("TLS_CLIENT_CERT_FILE", "")
TLS_CLIENT_KEY_FILE = os.getenv("TLS_CLIENT_KEY_FILE", "")
RUNS = int(os.getenv("RUNS", "30"))
DATA_SIZE_KB = int(os.getenv("DATA_SIZE_KB", "512"))
COMPLEXITY = float(os.getenv("COMPLEXITY", "1.0"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/app/results"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))


FIELDS = [
    "pipeline",
    "run_id",
    "input_id",
    "client_total_ms",
    "service_total_ms",
    "client_service_delta_ms",
    "security_profile",
    "transport_security",
    "network_ms",
    "security_ms",
    "tls_handshake_ms",
    "auth_ms",
    "crypto_ms",
    "replay_check_ms",
    "preprocess_ms",
    "inference_ms",
    "storage_ms",
    "sync_ms",
    "payload_sent_kb",
    "payload_synced_kb",
    "result_payload_kb",
    "security_overhead_kb",
]


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for pipeline in sorted({row["pipeline"] for row in rows}):
        subset = [row for row in rows if row["pipeline"] == pipeline]
        totals = [float(row["client_total_ms"]) for row in subset]
        summary[pipeline] = {
            "runs": len(subset),
            "client_total_ms": {
                "mean": statistics.fmean(totals),
                "p50": percentile(totals, 50),
                "p95": percentile(totals, 95),
                "p99": percentile(totals, 99),
                "min": min(totals),
                "max": max(totals),
            },
            "mean_network_ms": statistics.fmean(float(row["network_ms"]) for row in subset),
            "mean_security_ms": statistics.fmean(float(row["security_ms"]) for row in subset),
            "mean_client_service_delta_ms": statistics.fmean(
                float(row["client_service_delta_ms"]) for row in subset
            ),
            "mean_preprocess_ms": statistics.fmean(float(row["preprocess_ms"]) for row in subset),
            "mean_inference_ms": statistics.fmean(float(row["inference_ms"]) for row in subset),
            "mean_storage_ms": statistics.fmean(float(row["storage_ms"]) for row in subset),
            "mean_sync_ms": statistics.fmean(float(row["sync_ms"]) for row in subset),
            "mean_payload_sent_kb": statistics.fmean(float(row["payload_sent_kb"]) for row in subset),
            "mean_payload_synced_kb": statistics.fmean(float(row["payload_synced_kb"]) for row in subset),
        }
    return summary


def httpx_kwargs_for_url(url: str) -> dict[str, Any]:
    if not url.startswith("https://"):
        return {}

    context = ssl.create_default_context(cafile=TLS_CA_FILE if TLS_CA_FILE else None)
    if TLS_CLIENT_CERT_FILE and TLS_CLIENT_KEY_FILE:
        context.load_cert_chain(TLS_CLIENT_CERT_FILE, TLS_CLIENT_KEY_FILE)
    return {"verify": context}


async def run_one(
    url: str,
    pipeline: str,
    security_profile: str,
    run_id: int,
) -> dict[str, Any]:
    suffix = security_profile if security_profile != "none" else "plain"
    input_id = f"{pipeline}-{suffix}-{run_id:04d}"
    payload = {
        "input_id": input_id,
        "data_size_kb": DATA_SIZE_KB,
        "complexity": COMPLEXITY,
        "security_profile": security_profile,
    }

    start = time.perf_counter()
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS),
        **httpx_kwargs_for_url(url),
    ) as client:
        response = await client.post(url, json=payload)
        client_total_ms = (time.perf_counter() - start) * 1000

    response.raise_for_status()
    body = response.json()
    timings = body["timings_ms"]
    service_total_ms = float(body["total_ms"])

    return {
        "pipeline": body["pipeline"],
        "run_id": run_id,
        "input_id": input_id,
        "client_total_ms": round(client_total_ms, 3),
        "service_total_ms": round(service_total_ms, 3),
        "client_service_delta_ms": round(client_total_ms - service_total_ms, 3),
        "security_profile": body["security_profile"],
        "transport_security": body.get("transport_security", "plain"),
        "network_ms": round(float(timings.get("network_ms", 0.0)), 3),
        "security_ms": round(float(timings.get("security_ms", 0.0)), 3),
        "tls_handshake_ms": round(float(timings.get("tls_handshake_ms", 0.0)), 3),
        "auth_ms": round(float(timings.get("auth_ms", 0.0)), 3),
        "crypto_ms": round(float(timings.get("crypto_ms", 0.0)), 3),
        "replay_check_ms": round(float(timings.get("replay_check_ms", 0.0)), 3),
        "preprocess_ms": round(float(timings.get("preprocess_ms", 0.0)), 3),
        "inference_ms": round(float(timings.get("inference_ms", 0.0)), 3),
        "storage_ms": round(float(timings.get("storage_ms", 0.0)), 3),
        "sync_ms": round(float(timings.get("sync_ms", 0.0)), 3),
        "payload_sent_kb": round(float(body["payload_sent_kb"]), 3),
        "payload_synced_kb": round(float(body["payload_synced_kb"]), 3),
        "result_payload_kb": round(float(body["result_payload_kb"]), 3),
        "security_overhead_kb": round(float(body.get("security_overhead_kb", 0.0)), 3),
    }


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []

    targets = [
        ("cloud", CLOUD_URL, "cloud", "none"),
        ("edge", EDGE_URL, "edge", "none"),
        ("cloud_sim", CLOUD_URL, "cloud", "simulated"),
        ("edge_sim", EDGE_URL, "edge", "simulated"),
        ("cloud_tls", CLOUD_TLS_URL, "cloud", "tls"),
        ("edge_tls", EDGE_TLS_URL, "edge", "tls"),
    ]

    for run_id in range(1, RUNS + 1):
        run_rows = []
        for _, url, pipeline, security_profile in targets:
            row = await run_one(url, pipeline, security_profile, run_id)
            run_rows.append(row)
            rows.append(row)
        print(
            f"run={run_id:03d} "
            + " ".join(f"{row['pipeline']}={row['client_total_ms']:.1f}ms" for row in run_rows),
            flush=True,
        )

    results_path = OUTPUT_DIR / "results.csv"
    with results_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    summary = summarize(rows)
    summary_path = OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"wrote {results_path}")
    print(f"wrote {summary_path}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
