import asyncio
import json
import logging
import os
import ssl
import time
from typing import Any, Literal

import httpx
import uvicorn
from fastapi import FastAPI, Response
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from app.clinical import (
    cloud_pipeline_result,
    edge_pipeline_result,
    payload_size_kb,
    pseudonymize,
)


ROLE = os.getenv("ROLE", "cloud").lower()
SERVICE_NAME = os.getenv("SERVICE_NAME", ROLE)
EDGE_DEVICE_PROFILE = os.getenv("EDGE_DEVICE_PROFILE", "")
PORT = int(os.getenv("PORT", "8000"))
CLOUD_SYNC_URL = os.getenv("CLOUD_SYNC_URL", "")
TLS_CERT_FILE = os.getenv("TLS_CERT_FILE", "")
TLS_KEY_FILE = os.getenv("TLS_KEY_FILE", "")
TLS_CA_FILE = os.getenv("TLS_CA_FILE", "")
TLS_REQUIRE_CLIENT_CERT = os.getenv("TLS_REQUIRE_CLIENT_CERT", "false").lower() == "true"
TLS_CLIENT_CERT_FILE = os.getenv("TLS_CLIENT_CERT_FILE", "")
TLS_CLIENT_KEY_FILE = os.getenv("TLS_CLIENT_KEY_FILE", "")
TRANSPORT_SECURITY = os.getenv("TRANSPORT_SECURITY", "tls" if TLS_CERT_FILE else "plain")

NETWORK_UPLINK_MS = float(os.getenv("NETWORK_UPLINK_MS", "0"))
PREPROCESS_MS = float(os.getenv("PREPROCESS_MS", "20"))
INFERENCE_MS = float(os.getenv("INFERENCE_MS", "40"))
STORAGE_MS = float(os.getenv("STORAGE_MS", "10"))
RESULT_PAYLOAD_RATIO = float(os.getenv("RESULT_PAYLOAD_RATIO", "0.05"))

SECURE_TLS_HANDSHAKE_MS = float(os.getenv("SECURE_TLS_HANDSHAKE_MS", "18"))
SECURE_AUTH_MS = float(os.getenv("SECURE_AUTH_MS", "4"))
SECURE_CRYPTO_MS_PER_MB = float(os.getenv("SECURE_CRYPTO_MS_PER_MB", "7"))
SECURE_REPLAY_CHECK_MS = float(os.getenv("SECURE_REPLAY_CHECK_MS", "2"))
SECURE_PACKET_OVERHEAD_KB = float(os.getenv("SECURE_PACKET_OVERHEAD_KB", "2"))
PIPELINE_STEP_LOGS = os.getenv("PIPELINE_STEP_LOGS", "true").lower() == "true"


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("pipeline")


app = FastAPI(
    title=f"{SERVICE_NAME} benchmark API",
    description="Synthetic cloud/edge pipeline service with Prometheus metrics.",
    version="1.0.0",
)


REQUESTS = Counter(
    "pipeline_requests_total",
    "Total processed pipeline requests.",
    ["service", "pipeline", "endpoint"],
)
STAGE_LATENCY = Histogram(
    "pipeline_stage_latency_ms",
    "Latency per pipeline stage in milliseconds.",
    ["service", "pipeline", "stage"],
    buckets=(1, 5, 10, 20, 40, 80, 120, 200, 400, 800, 1600, 3200),
)
TOTAL_LATENCY = Histogram(
    "pipeline_total_latency_ms",
    "Total request latency in milliseconds.",
    ["service", "pipeline"],
    buckets=(10, 25, 50, 100, 150, 250, 400, 800, 1200, 2000, 5000),
)
PAYLOAD_SIZE = Histogram(
    "pipeline_payload_size_kb",
    "Logical payload size in KB.",
    ["service", "pipeline", "kind"],
    buckets=(1, 8, 32, 128, 512, 1024, 2048, 4096, 8192),
)
IN_FLIGHT = Gauge(
    "pipeline_in_flight_requests",
    "Requests currently being processed.",
    ["service", "pipeline"],
)
class ProcessRequest(BaseModel):
    input_id: str = Field(..., examples=["sample-001"])
    data_size_kb: int = Field(512, ge=1, le=65536)
    complexity: float = Field(1.0, ge=0.1, le=10.0)
    security_profile: Literal["none", "secure", "simulated", "tls"] = "none"
    patient_record: dict[str, Any] | None = None
    initial_risk_assessment: dict[str, Any] | None = None


class SyncRequest(BaseModel):
    input_id: str
    source: str = "edge"
    result_payload_kb: float
    security_profile: Literal["none", "secure", "simulated", "tls"] = "none"
    clinical_summary: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def now_ms() -> float:
    return time.perf_counter() * 1000


def patient_log_context(patient: dict[str, Any] | None) -> dict[str, Any]:
    if not patient:
        return {"data_source": "synthetic_payload"}

    return {
        "data_source": "patient_record",
        "patient_hash": pseudonymize(str(patient.get("patient_id", ""))),
        "ward": patient.get("ward"),
        "bed": patient.get("bed"),
        "diagnosis": patient.get("primary_diagnosis"),
        "vital_samples": len(patient.get("vitals", [])) if isinstance(patient.get("vitals"), list) else 0,
        "clinical_fields": [
            key
            for key in [
                "age",
                "sex",
                "ward",
                "bed",
                "primary_diagnosis",
                "comorbidities",
                "medications",
                "vitals",
            ]
            if key in patient
        ],
    }


def log_pipeline_step(
    step: str,
    status: str,
    pipeline: str,
    input_id: str,
    patient: dict[str, Any] | None,
    **details: Any,
) -> None:
    if not PIPELINE_STEP_LOGS:
        return

    if status == "start":
        logger.info("#######-------- INIZIO STEP PIPELINE: %s -------- ######", step.upper())

    event = {
        "event": "clinical_pipeline_step",
        "service": SERVICE_NAME,
        "role": ROLE,
        "pipeline": pipeline,
        "input_id": input_id,
        "step": step,
        "status": status,
        "edge_device_profile": EDGE_DEVICE_PROFILE if ROLE == "edge" else "",
        **patient_log_context(patient),
        **details,
    }
    logger.info(json.dumps(event, separators=(",", ":"), sort_keys=True, default=str))


def busy_work(duration_ms: float) -> None:
    deadline = time.perf_counter() + max(duration_ms, 0) / 1000
    value = 0
    while time.perf_counter() < deadline:
        value = (value * 1664525 + 1013904223) % 4294967296
    if value == -1:
        print("unreachable")


async def timed_async_sleep(stage: str, pipeline: str, duration_ms: float) -> float:
    start = now_ms()
    await asyncio.sleep(max(duration_ms, 0) / 1000)
    elapsed = now_ms() - start
    STAGE_LATENCY.labels(SERVICE_NAME, pipeline, stage).observe(elapsed)
    return elapsed


async def timed_cpu_stage(stage: str, pipeline: str, duration_ms: float) -> float:
    start = now_ms()
    await asyncio.to_thread(busy_work, duration_ms)
    elapsed = now_ms() - start
    STAGE_LATENCY.labels(SERVICE_NAME, pipeline, stage).observe(elapsed)
    return elapsed


def pipeline_label(base_pipeline: str, security_profile: str) -> str:
    normalized_profile = normalize_security_profile(security_profile)
    if normalized_profile == "simulated":
        return f"{base_pipeline}_simulated_secure"
    if normalized_profile == "tls":
        return f"{base_pipeline}_tls"
    return base_pipeline


def normalize_security_profile(security_profile: str) -> str:
    if security_profile == "secure":
        return "simulated"
    return security_profile


async def apply_security_profile(security_profile: str, pipeline: str, payload_kb: float) -> dict[str, float]:
    normalized_profile = normalize_security_profile(security_profile)
    if normalized_profile != "simulated":
        return {
            "security_ms": 0.0,
            "tls_handshake_ms": 0.0,
            "auth_ms": 0.0,
            "crypto_ms": 0.0,
            "replay_check_ms": 0.0,
            "security_overhead_kb": 0.0,
        }

    tls_handshake_ms = await timed_async_sleep("security_tls_handshake", pipeline, SECURE_TLS_HANDSHAKE_MS)
    auth_ms = await timed_cpu_stage("security_hmac_auth", pipeline, SECURE_AUTH_MS)
    crypto_target_ms = SECURE_CRYPTO_MS_PER_MB * (payload_kb / 1024)
    crypto_ms = await timed_cpu_stage("security_encrypt_decrypt", pipeline, crypto_target_ms)
    replay_check_ms = await timed_async_sleep("security_replay_check", pipeline, SECURE_REPLAY_CHECK_MS)

    return {
        "security_ms": tls_handshake_ms + auth_ms + crypto_ms + replay_check_ms,
        "tls_handshake_ms": tls_handshake_ms,
        "auth_ms": auth_ms,
        "crypto_ms": crypto_ms,
        "replay_check_ms": replay_check_ms,
        "security_overhead_kb": SECURE_PACKET_OVERHEAD_KB,
    }


def httpx_tls_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if CLOUD_SYNC_URL.startswith("https://"):
        context = ssl.create_default_context(cafile=TLS_CA_FILE if TLS_CA_FILE else None)
        if TLS_CLIENT_CERT_FILE and TLS_CLIENT_KEY_FILE:
            context.load_cert_chain(TLS_CLIENT_CERT_FILE, TLS_CLIENT_KEY_FILE)
        kwargs["verify"] = context
    return kwargs


async def sync_to_cloud(
    input_id: str,
    result_payload_kb: float,
    local_timings: dict[str, float],
    security_profile: str,
    clinical_summary: dict[str, Any] | None,
) -> float:
    if not CLOUD_SYNC_URL:
        return 0.0

    logger.info(
        json.dumps(
            {
                "event": "edge_cloud_sync",
                "service": SERVICE_NAME,
                "role": ROLE,
                "input_id": input_id,
                "destination": CLOUD_SYNC_URL,
                "payload_kind": "reduced_clinical_summary",
                "result_payload_kb": result_payload_kb,
                "security_profile": security_profile,
            },
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        )
    )
    start = now_ms()
    payload = {
        "input_id": input_id,
        "source": "edge",
        "result_payload_kb": result_payload_kb,
        "security_profile": security_profile,
        "clinical_summary": clinical_summary,
        "metadata": {"local_timings_ms": local_timings},
    }
    try:
        async with httpx.AsyncClient(timeout=10, **httpx_tls_kwargs()) as client:
            response = await client.post(CLOUD_SYNC_URL, json=payload)
            response.raise_for_status()
    except Exception:
        return now_ms() - start
    return now_ms() - start


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "role": ROLE, "edge_device_profile": EDGE_DEVICE_PROFILE}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/process")
async def process(request: ProcessRequest) -> dict[str, Any]:
    base_pipeline = "edge" if ROLE == "edge" else "cloud"
    security_profile = normalize_security_profile(request.security_profile)
    pipeline = pipeline_label(base_pipeline, security_profile)
    REQUESTS.labels(SERVICE_NAME, pipeline, "process").inc()
    payload_sent_kb = payload_size_kb(request.patient_record) if request.patient_record else float(request.data_size_kb)
    PAYLOAD_SIZE.labels(SERVICE_NAME, pipeline, "input").observe(payload_sent_kb)
    IN_FLIGHT.labels(SERVICE_NAME, pipeline).inc()

    total_start = now_ms()
    try:
        log_pipeline_step(
            "request_received",
            "start",
            pipeline,
            request.input_id,
            request.patient_record,
            payload_sent_kb=round(payload_sent_kb, 3),
            security_profile=security_profile,
            transport_security=TRANSPORT_SECURITY,
            initial_risk_score=(request.initial_risk_assessment or {}).get("risk_score"),
            initial_risk_level=(request.initial_risk_assessment or {}).get("risk_level"),
            cloud_sync_enabled=bool(CLOUD_SYNC_URL),
        )
        log_pipeline_step(
            "network_uplink",
            "start",
            pipeline,
            request.input_id,
            request.patient_record,
            simulated_delay_ms=NETWORK_UPLINK_MS,
        )
        network_ms = await timed_async_sleep("network_uplink", pipeline, NETWORK_UPLINK_MS)
        log_pipeline_step(
            "network_uplink",
            "done",
            pipeline,
            request.input_id,
            request.patient_record,
            elapsed_ms=round(network_ms, 3),
        )

        log_pipeline_step(
            "transport_security",
            "start",
            pipeline,
            request.input_id,
            request.patient_record,
            profile=security_profile,
            transport_status="active" if security_profile == "tls" else "simulated" if security_profile == "simulated" else "skipped",
            payload_kb=round(payload_sent_kb, 3),
            note="real_tls_terminates_before_application" if security_profile == "tls" else "",
        )
        security_timings = await apply_security_profile(
            security_profile,
            pipeline,
            payload_sent_kb,
        )
        if security_profile == "simulated":
            log_pipeline_step(
                "transport_security",
                "done",
                pipeline,
                request.input_id,
                request.patient_record,
                elapsed_ms=round(security_timings["security_ms"], 3),
                overhead_kb=security_timings["security_overhead_kb"],
            )

        if request.patient_record:
            log_pipeline_step(
                "wearable_payload_validation",
                "start",
                pipeline,
                request.input_id,
                request.patient_record,
                operations=[
                    "schema_validation",
                    "wearable_sample_validation",
                    "required_vital_fields_check",
                ],
            )
            preprocess_ms = await timed_cpu_stage("wearable_payload_validation", pipeline, PREPROCESS_MS * request.complexity)
            log_pipeline_step(
                "wearable_payload_validation",
                "done",
                pipeline,
                request.input_id,
                request.patient_record,
                elapsed_ms=round(preprocess_ms, 3),
            )
            log_pipeline_step(
                "abnormal_threshold_check",
                "start",
                pipeline,
                request.input_id,
                request.patient_record,
                operations=[
                    "latest_vitals_extraction",
                    "normal_range_comparison",
                    "alert_generation",
                ],
            )
            if base_pipeline == "cloud":
                clinical_result = cloud_pipeline_result(request.patient_record)
            else:
                clinical_result = edge_pipeline_result(request.patient_record)
            inference_ms = await timed_cpu_stage("abnormal_threshold_check", pipeline, INFERENCE_MS * request.complexity)
            result_payload_kb = payload_size_kb(clinical_result["clinical_payload"])
            risk = clinical_result["risk"]
            log_pipeline_step(
                "abnormal_threshold_check",
                "done",
                pipeline,
                request.input_id,
                request.patient_record,
                elapsed_ms=round(inference_ms, 3),
                validation_errors=clinical_result["validation_errors"],
                risk_score=risk["risk_score"],
                risk_level=risk["risk_level"],
                abnormal_vitals=risk.get("abnormal_vitals", []),
                alert=clinical_result["alert"],
                result_payload_kb=round(result_payload_kb, 3),
                output_payload=clinical_result["processing_mode"],
            )
        else:
            log_pipeline_step(
                "synthetic_preprocess",
                "start",
                pipeline,
                request.input_id,
                None,
                data_size_kb=request.data_size_kb,
            )
            preprocess_ms = await timed_cpu_stage("preprocess", pipeline, PREPROCESS_MS * request.complexity)
            inference_ms = await timed_cpu_stage("inference", pipeline, INFERENCE_MS * request.complexity)
            result_payload_kb = max(1.0, payload_sent_kb * RESULT_PAYLOAD_RATIO)
            clinical_result = {
                "processing_mode": "synthetic_payload",
                "validation_errors": [],
                "risk": None,
                "alert": False,
                "clinical_payload": {},
            }

        PAYLOAD_SIZE.labels(SERVICE_NAME, pipeline, "result").observe(result_payload_kb)

        timings = {
            "network_ms": network_ms,
            **security_timings,
            "preprocess_ms": preprocess_ms,
            "inference_ms": inference_ms,
        }

        if base_pipeline == "cloud":
            log_pipeline_step(
                "cloud_storage",
                "start",
                pipeline,
                request.input_id,
                request.patient_record,
                stored_payload="full_patient_record" if request.patient_record else "synthetic_result",
            )
            storage_ms = await timed_async_sleep("storage", pipeline, STORAGE_MS)
            log_pipeline_step(
                "cloud_storage",
                "done",
                pipeline,
                request.input_id,
                request.patient_record,
                elapsed_ms=round(storage_ms, 3),
            )
            timings["storage_ms"] = storage_ms
            timings["sync_ms"] = 0.0
            payload_synced_kb = payload_sent_kb
        else:
            sync_ms = 0.0
            if CLOUD_SYNC_URL:
                log_pipeline_step(
                    "edge_to_cloud_sync",
                    "start",
                    pipeline,
                    request.input_id,
                    request.patient_record,
                    synced_payload="reduced_clinical_summary",
                    destination=CLOUD_SYNC_URL,
                )
                sync_ms = await sync_to_cloud(
                    request.input_id,
                    result_payload_kb,
                    timings,
                    security_profile,
                    clinical_result["clinical_payload"],
                )
                STAGE_LATENCY.labels(SERVICE_NAME, pipeline, "cloud_sync").observe(sync_ms)
                log_pipeline_step(
                    "edge_to_cloud_sync",
                    "done",
                    pipeline,
                    request.input_id,
                    request.patient_record,
                    elapsed_ms=round(sync_ms, 3),
                    payload_synced_kb=round(result_payload_kb, 3),
                )
            timings["storage_ms"] = 0.0
            timings["sync_ms"] = sync_ms
            payload_synced_kb = result_payload_kb if CLOUD_SYNC_URL else 0.0

        total_ms = now_ms() - total_start
        TOTAL_LATENCY.labels(SERVICE_NAME, pipeline).observe(total_ms)
        log_pipeline_step(
            "dashboard_response",
            "start",
            pipeline,
            request.input_id,
            request.patient_record,
            response_payload="patient_alert",
            payload_synced_kb=round(payload_synced_kb, 3),
        )
        log_pipeline_step(
            "dashboard_response",
            "done",
            pipeline,
            request.input_id,
            request.patient_record,
            total_ms=round(total_ms, 3),
            response_payload="patient_alert",
            payload_synced_kb=round(payload_synced_kb, 3),
        )

        return {
            "pipeline": pipeline,
            "service": SERVICE_NAME,
            "security_profile": security_profile,
            "transport_security": TRANSPORT_SECURITY,
            "initial_risk_assessment": request.initial_risk_assessment,
            "input_id": request.input_id,
            "payload_sent_kb": payload_sent_kb,
            "payload_synced_kb": payload_synced_kb,
            "result_payload_kb": result_payload_kb,
            "security_overhead_kb": security_timings["security_overhead_kb"],
            "clinical": clinical_result,
            "timings_ms": timings,
            "total_ms": total_ms,
        }
    finally:
        IN_FLIGHT.labels(SERVICE_NAME, pipeline).dec()


@app.post("/sync")
async def sync(request: SyncRequest) -> dict[str, Any]:
    security_profile = normalize_security_profile(request.security_profile)
    pipeline = pipeline_label("edge-sync", security_profile)
    REQUESTS.labels(SERVICE_NAME, pipeline, "sync").inc()
    PAYLOAD_SIZE.labels(SERVICE_NAME, pipeline, "result").observe(request.result_payload_kb)
    log_pipeline_step(
        "edge_summary_received",
        "start",
        pipeline,
        request.input_id,
        None,
        source=request.source,
        payload_kind="reduced_clinical_summary",
        result_payload_kb=round(request.result_payload_kb, 3),
        security_profile=security_profile,
    )
    security_timings = await apply_security_profile(
        security_profile,
        pipeline,
        request.result_payload_kb,
    )
    log_pipeline_step(
        "edge_summary_storage",
        "start",
        pipeline,
        request.input_id,
        None,
        stored_payload="edge_reduced_clinical_summary",
    )
    storage_ms = await timed_async_sleep("storage", pipeline, STORAGE_MS)
    log_pipeline_step(
        "edge_summary_storage",
        "done",
        pipeline,
        request.input_id,
        None,
        security_ms=round(security_timings["security_ms"], 3),
        storage_ms=round(storage_ms, 3),
    )
    return {
        "status": "stored",
        "service": SERVICE_NAME,
        "input_id": request.input_id,
        "source": request.source,
        "security_profile": security_profile,
        "transport_security": TRANSPORT_SECURITY,
        "stored_payload": "edge_reduced_clinical_summary",
        "clinical_summary": request.clinical_summary,
        "security_ms": security_timings["security_ms"],
        "storage_ms": storage_ms,
    }


if __name__ == "__main__":
    ssl_kwargs: dict[str, Any] = {}
    if TLS_CERT_FILE and TLS_KEY_FILE:
        ssl_kwargs = {
            "ssl_certfile": TLS_CERT_FILE,
            "ssl_keyfile": TLS_KEY_FILE,
        }
        if TLS_REQUIRE_CLIENT_CERT:
            ssl_kwargs["ssl_cert_reqs"] = ssl.CERT_REQUIRED
            ssl_kwargs["ssl_ca_certs"] = TLS_CA_FILE

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info", **ssl_kwargs)
