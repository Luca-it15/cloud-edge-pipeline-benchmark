import asyncio
import os
import ssl
import time
from typing import Any, Literal

import httpx
import uvicorn
from fastapi import FastAPI, Response
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest


ROLE = os.getenv("ROLE", "cloud").lower()
SERVICE_NAME = os.getenv("SERVICE_NAME", ROLE)
PORT = int(os.getenv("PORT", "8000"))
CLOUD_SYNC_URL = os.getenv("CLOUD_SYNC_URL", "")
TLS_CERT_FILE = os.getenv("TLS_CERT_FILE", "")
TLS_KEY_FILE = os.getenv("TLS_KEY_FILE", "")
TLS_CA_FILE = os.getenv("TLS_CA_FILE", "")
TLS_REQUIRE_CLIENT_CERT = os.getenv("TLS_REQUIRE_CLIENT_CERT", "false").lower() == "true"
TLS_CLIENT_CERT_FILE = os.getenv("TLS_CLIENT_CERT_FILE", "")
TLS_CLIENT_KEY_FILE = os.getenv("TLS_CLIENT_KEY_FILE", "")

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


class SyncRequest(BaseModel):
    input_id: str
    source: str = "edge"
    result_payload_kb: float
    security_profile: Literal["none", "secure", "simulated", "tls"] = "none"
    metadata: dict[str, Any] = Field(default_factory=dict)


def now_ms() -> float:
    return time.perf_counter() * 1000


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
) -> float:
    if not CLOUD_SYNC_URL:
        return 0.0

    start = now_ms()
    payload = {
        "input_id": input_id,
        "source": "edge",
        "result_payload_kb": result_payload_kb,
        "security_profile": security_profile,
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
    return {"status": "ok", "service": SERVICE_NAME, "role": ROLE}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/process")
async def process(request: ProcessRequest) -> dict[str, Any]:
    base_pipeline = "edge" if ROLE == "edge" else "cloud"
    security_profile = normalize_security_profile(request.security_profile)
    pipeline = pipeline_label(base_pipeline, security_profile)
    REQUESTS.labels(SERVICE_NAME, pipeline, "process").inc()
    PAYLOAD_SIZE.labels(SERVICE_NAME, pipeline, "input").observe(request.data_size_kb)
    IN_FLIGHT.labels(SERVICE_NAME, pipeline).inc()

    total_start = now_ms()
    try:
        network_ms = await timed_async_sleep("network_uplink", pipeline, NETWORK_UPLINK_MS)
        security_timings = await apply_security_profile(
            security_profile,
            pipeline,
            float(request.data_size_kb),
        )
        preprocess_ms = await timed_cpu_stage("preprocess", pipeline, PREPROCESS_MS * request.complexity)
        inference_ms = await timed_cpu_stage("inference", pipeline, INFERENCE_MS * request.complexity)

        result_payload_kb = max(1.0, request.data_size_kb * RESULT_PAYLOAD_RATIO)
        PAYLOAD_SIZE.labels(SERVICE_NAME, pipeline, "result").observe(result_payload_kb)

        timings = {
            "network_ms": network_ms,
            **security_timings,
            "preprocess_ms": preprocess_ms,
            "inference_ms": inference_ms,
        }

        if base_pipeline == "cloud":
            storage_ms = await timed_async_sleep("storage", pipeline, STORAGE_MS)
            timings["storage_ms"] = storage_ms
            timings["sync_ms"] = 0.0
            payload_synced_kb = request.data_size_kb
        else:
            sync_ms = await sync_to_cloud(
                request.input_id,
                result_payload_kb,
                timings,
                security_profile,
            )
            STAGE_LATENCY.labels(SERVICE_NAME, pipeline, "cloud_sync").observe(sync_ms)
            timings["storage_ms"] = 0.0
            timings["sync_ms"] = sync_ms
            payload_synced_kb = result_payload_kb

        total_ms = now_ms() - total_start
        TOTAL_LATENCY.labels(SERVICE_NAME, pipeline).observe(total_ms)

        return {
            "pipeline": pipeline,
            "service": SERVICE_NAME,
            "security_profile": security_profile,
            "transport_security": "tls" if TLS_CERT_FILE else "plain",
            "input_id": request.input_id,
            "payload_sent_kb": request.data_size_kb,
            "payload_synced_kb": payload_synced_kb,
            "result_payload_kb": result_payload_kb,
            "security_overhead_kb": security_timings["security_overhead_kb"],
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
    security_timings = await apply_security_profile(
        security_profile,
        pipeline,
        request.result_payload_kb,
    )
    storage_ms = await timed_async_sleep("storage", pipeline, STORAGE_MS)
    return {
        "status": "stored",
        "service": SERVICE_NAME,
        "input_id": request.input_id,
        "source": request.source,
        "security_profile": security_profile,
        "transport_security": "tls" if TLS_CERT_FILE else "plain",
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
