import asyncio
import csv
import hashlib
import json
import os
import statistics
import ssl
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


CLOUD_URL = os.getenv("CLOUD_URL", "http://cloud-api:8000/process")
EDGE_URL = os.getenv("EDGE_URL", "http://edge-api:8000/process")
CLOUD_TLS_URL = os.getenv("CLOUD_TLS_URL", "https://cloud-api-tls:8443/process")
EDGE_TLS_URL = os.getenv("EDGE_TLS_URL", "https://edge-api-tls:8443/process")
TLS_CA_FILE = os.getenv("TLS_CA_FILE", "")
TLS_CLIENT_CERT_FILE = os.getenv("TLS_CLIENT_CERT_FILE", "")
TLS_CLIENT_KEY_FILE = os.getenv("TLS_CLIENT_KEY_FILE", "")
DATASET_PATH = Path(os.getenv("DATASET_PATH", "/app/data/patients.json"))
DATASET_REPEATS = int(os.getenv("DATASET_REPEATS", "3"))
COMPLEXITY = float(os.getenv("COMPLEXITY", "1.0"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/app/results"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
BENCHMARK_SCENARIOS = os.getenv(
    "BENCHMARK_SCENARIOS",
    "cloud,edge,edge_tls",
)


FIELDS = [
    "pipeline",
    "run_id",
    "repeat",
    "input_id",
    "patient_id",
    "patient_name",
    "ward",
    "bed",
    "diagnosis",
    "client_total_ms",
    "service_total_ms",
    "client_service_delta_ms",
    "security_profile",
    "transport_security",
    "cold_start_candidate",
    "process_age_ms",
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
    "abnormal_vitals_count",
    "abnormal_vitals",
    "risk_score",
    "risk_level",
    "recommended_action",
    "processing_mode",
    "alert",
]


def patient_hash(patient_id: str) -> str:
    return hashlib.sha256(patient_id.encode("utf-8")).hexdigest()[:12]


def log_event(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **fields}, separators=(",", ":"), sort_keys=True, default=str), flush=True)


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
            "cold_start_requests": sum(1 for row in subset if row["cold_start_candidate"] == "true"),
            "mean_preprocess_ms": statistics.fmean(float(row["preprocess_ms"]) for row in subset),
            "mean_inference_ms": statistics.fmean(float(row["inference_ms"]) for row in subset),
            "mean_storage_ms": statistics.fmean(float(row["storage_ms"]) for row in subset),
            "mean_sync_ms": statistics.fmean(float(row["sync_ms"]) for row in subset),
            "mean_payload_sent_kb": statistics.fmean(float(row["payload_sent_kb"]) for row in subset),
            "mean_payload_synced_kb": statistics.fmean(float(row["payload_synced_kb"]) for row in subset),
            "alerts": sum(1 for row in subset if row["alert"] == "true"),
            "mean_abnormal_vitals": statistics.fmean(float(row["abnormal_vitals_count"]) for row in subset),
            "critical_patients": sum(1 for row in subset if row["risk_level"] == "critical"),
            "high_patients": sum(1 for row in subset if row["risk_level"] == "high"),
        }
    return summary


def httpx_kwargs_for_url(url: str) -> dict[str, Any]:
    if not url.startswith("https://"):
        return {}

    host = urlparse(url).hostname or ""
    local_tls_host = host in {"edge-api-tls", "localhost", "127.0.0.1"}
    context = ssl.create_default_context(cafile=TLS_CA_FILE if local_tls_host and TLS_CA_FILE else None)
    if local_tls_host and TLS_CLIENT_CERT_FILE and TLS_CLIENT_KEY_FILE:
        context.load_cert_chain(TLS_CLIENT_CERT_FILE, TLS_CLIENT_KEY_FILE)
    return {"verify": context}


async def run_one(
    url: str,
    pipeline: str,
    security_profile: str,
    run_id: int,
    repeat: int,
    patient: dict[str, Any],
) -> dict[str, Any]:
    suffix = security_profile if security_profile != "none" else "plain"
    input_id = f"{pipeline}-{suffix}-r{repeat}-{patient['patient_id']}-{run_id:04d}"
    payload = {
        "input_id": input_id,
        "complexity": COMPLEXITY,
        "security_profile": security_profile,
        "patient_record": patient,
    }

    log_event(
        "benchmark_pipeline_step",
        step="request_start",
        pipeline=pipeline,
        security_profile=security_profile,
        repeat=repeat,
        input_id=input_id,
        patient_hash=patient_hash(patient["patient_id"]),
        ward=patient["ward"],
        bed=patient["bed"],
        diagnosis=patient["primary_diagnosis"],
        vital_samples=len(patient.get("vitals", [])),
        endpoint=url,
    )
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
    clinical = body["clinical"]
    risk = clinical["risk"] or {}
    abnormal_vitals = risk.get("abnormal_vitals", [])

    row = {
        "pipeline": body["pipeline"],
        "run_id": run_id,
        "repeat": repeat,
        "input_id": input_id,
        "patient_id": patient["patient_id"],
        "patient_name": patient["name"],
        "ward": patient["ward"],
        "bed": patient["bed"],
        "diagnosis": patient["primary_diagnosis"],
        "client_total_ms": round(client_total_ms, 3),
        "service_total_ms": round(service_total_ms, 3),
        "client_service_delta_ms": round(client_total_ms - service_total_ms, 3),
        "security_profile": body["security_profile"],
        "transport_security": body.get("transport_security", "plain"),
        "cold_start_candidate": "true" if body.get("cold_start_candidate") else "false",
        "process_age_ms": round(float(body.get("process_age_ms", 0.0)), 3),
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
        "abnormal_vitals_count": len(abnormal_vitals),
        "abnormal_vitals": json.dumps(abnormal_vitals, separators=(",", ":")),
        "risk_score": risk.get("risk_score", 0),
        "risk_level": risk.get("risk_level", "unknown"),
        "recommended_action": risk.get("recommended_action", ""),
        "processing_mode": clinical["processing_mode"],
        "alert": "true" if clinical["alert"] else "false",
        "_clinical": clinical,
    }
    log_event(
        "benchmark_pipeline_step",
        step="request_done",
        pipeline=row["pipeline"],
        security_profile=row["security_profile"],
        input_id=input_id,
        repeat=repeat,
        patient_hash=patient_hash(patient["patient_id"]),
        risk_score=row["risk_score"],
        risk_level=row["risk_level"],
        alert=row["alert"] == "true",
        client_total_ms=row["client_total_ms"],
        service_total_ms=row["service_total_ms"],
        cold_start_candidate=row["cold_start_candidate"] == "true",
        process_age_ms=row["process_age_ms"],
        payload_sent_kb=row["payload_sent_kb"],
        payload_synced_kb=row["payload_synced_kb"],
        abnormal_vitals_count=row["abnormal_vitals_count"],
    )
    return row


def load_patients() -> list[dict[str, Any]]:
    patients = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    if not isinstance(patients, list) or not patients:
        raise ValueError(f"Dataset must be a non-empty JSON list: {DATASET_PATH}")
    return patients


def dashboard_payload(rows: list[dict[str, Any]], patients: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    patient_index = {patient["patient_id"]: patient for patient in patients}
    latest_by_patient: dict[str, dict[str, Any]] = {}
    comparisons: dict[str, dict[str, Any]] = {}

    for row in rows:
        patient_id = row["patient_id"]
        comparisons.setdefault(patient_id, {})[row["pipeline"]] = {
            "client_total_ms": row["client_total_ms"],
            "service_total_ms": row["service_total_ms"],
            "transport_security": row["transport_security"],
            "payload_sent_kb": row["payload_sent_kb"],
            "cold_start_candidate": row["cold_start_candidate"],
            "risk_score": row["risk_score"],
            "risk_level": row["risk_level"],
            "alert": row["alert"] == "true",
        }
        if row["pipeline"] in {"edge", "edge_tls"}:
            current = latest_by_patient.get(patient_id)
            if current is None or row["pipeline"] == "edge_tls":
                latest_by_patient[patient_id] = row

    patients_payload = []
    for patient_id, row in latest_by_patient.items():
        patient = patient_index[patient_id]
        latest_vitals = patient["vitals"][-1]
        patients_payload.append(
            {
                "patient_id": patient_id,
                "name": patient["name"],
                "age": patient["age"],
                "sex": patient["sex"],
                "ward": patient["ward"],
                "bed": patient["bed"],
                "diagnosis": patient["primary_diagnosis"],
                "comorbidities": patient.get("comorbidities", []),
                "medications": patient.get("medications", []),
                "latest_vitals": latest_vitals,
                "risk_score": row["risk_score"],
                "risk_level": row["risk_level"],
                "recommended_action": row["recommended_action"],
                "abnormal_vitals": (row.get("_clinical", {}).get("risk") or {}).get("abnormal_vitals", []),
                "alert": row["alert"] == "true",
                "pipeline_comparison": comparisons.get(patient_id, {}),
            }
        )

    risk_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for patient in patients_payload:
        risk_counts[patient["risk_level"]] = risk_counts.get(patient["risk_level"], 0) + 1

    ward_counts: dict[str, dict[str, int]] = {}
    for patient in patients_payload:
        ward = patient["ward"]
        ward_counts.setdefault(ward, {"patients": 0, "alerts": 0})
        ward_counts[ward]["patients"] += 1
        if patient["alert"]:
            ward_counts[ward]["alerts"] += 1

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset_size": len(patients),
        "scenarios": sorted(summary.keys()),
        "summary": summary,
        "risk_counts": risk_counts,
        "ward_counts": ward_counts,
        "patients": sorted(
            patients_payload,
            key=lambda item: ({"critical": 0, "high": 1, "medium": 2, "low": 3}.get(item["risk_level"], 9), item["ward"]),
        ),
        "results": [
            {key: value for key, value in row.items() if not key.startswith("_")}
            for row in rows
        ],
    }


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    patients = load_patients()
    rows: list[dict[str, Any]] = []

    scenario_definitions = {
        "cloud": (CLOUD_URL, "cloud", "none"),
        "edge": (EDGE_URL, "edge", "none"),
        "cloud_tls": (CLOUD_TLS_URL, "cloud", "tls"),
        "edge_tls": (EDGE_TLS_URL, "edge", "tls"),
    }
    requested_scenarios = [
        scenario.strip()
        for scenario in BENCHMARK_SCENARIOS.split(",")
        if scenario.strip()
    ]
    unknown_scenarios = [
        scenario
        for scenario in requested_scenarios
        if scenario not in scenario_definitions
    ]
    if unknown_scenarios:
        known = ", ".join(sorted(scenario_definitions))
        raise ValueError(f"Unknown benchmark scenarios: {unknown_scenarios}. Known scenarios: {known}")
    targets = [scenario_definitions[scenario] for scenario in requested_scenarios]
    log_event(
        "benchmark_run_start",
        dataset_path=str(DATASET_PATH),
        dataset_size=len(patients),
        dataset_repeats=DATASET_REPEATS,
        scenarios=requested_scenarios,
        cloud_url=CLOUD_URL,
        edge_url=EDGE_URL,
        complexity=COMPLEXITY,
    )

    run_id = 0
    for repeat in range(1, DATASET_REPEATS + 1):
        for patient in patients:
            run_id += 1
            run_rows = await asyncio.gather(
                *[
                    run_one(url, pipeline, security_profile, run_id, repeat, patient)
                    for url, pipeline, security_profile in targets
                ]
            )
            rows.extend(run_rows)
            max_risk = max(row["risk_score"] for row in run_rows)
            print(
                f"patient={patient['patient_id']} repeat={repeat} max_risk={max_risk} "
                + " ".join(f"{row['pipeline']}={row['client_total_ms']:.1f}ms" for row in run_rows),
                flush=True,
            )

    results_path = OUTPUT_DIR / "results.csv"
    with results_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows([{key: row[key] for key in FIELDS} for row in rows])

    summary = summarize(rows)
    summary_path = OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    dashboard_path = OUTPUT_DIR / "patient_results.json"
    dashboard_path.write_text(json.dumps(dashboard_payload(rows, patients, summary), indent=2), encoding="utf-8")

    log_event(
        "benchmark_run_done",
        results_path=str(results_path),
        summary_path=str(summary_path),
        dashboard_path=str(dashboard_path),
        rows=len(rows),
    )
    print(f"wrote {results_path}")
    print(f"wrote {summary_path}")
    print(f"wrote {dashboard_path}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
