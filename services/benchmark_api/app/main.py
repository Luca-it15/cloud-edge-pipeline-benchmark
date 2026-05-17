import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


PORT = int(os.getenv("PORT", "8090"))
BENCHMARK_SCRIPT = Path(os.getenv("BENCHMARK_SCRIPT", "/app/benchmark.py"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/app/results"))
DATASET_PATH = os.getenv("DATASET_PATH", "/app/data/patients.json")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("benchmark-control")

RUN_ENV_KEYS = [
    "CLOUD_URL",
    "EDGE_URL",
    "CLOUD_TLS_URL",
    "EDGE_TLS_URL",
    "TLS_CA_FILE",
    "TLS_CLIENT_CERT_FILE",
    "TLS_CLIENT_KEY_FILE",
    "DATASET_PATH",
    "DATASET_REPEATS",
    "COMPLEXITY",
    "OUTPUT_DIR",
    "REQUEST_TIMEOUT_SECONDS",
    "BENCHMARK_SCENARIOS",
]


class RunRequest(BaseModel):
    force: bool = False


class BenchmarkState:
    def __init__(self) -> None:
        self.process: asyncio.subprocess.Process | None = None
        self.status = "idle"
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.return_code: int | None = None
        self.error: str | None = None
        self.output_tail: list[str] = []
        self.lock = asyncio.Lock()

    def snapshot(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "running": self.status == "running",
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "return_code": self.return_code,
            "error": self.error,
            "output_tail": self.output_tail[-40:],
            "scenarios": os.getenv("BENCHMARK_SCENARIOS", ""),
            "output_dir": str(OUTPUT_DIR),
        }


state = BenchmarkState()
app = FastAPI(title="Benchmark Control API", version="1.0.0")


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def benchmark_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("DATASET_PATH", DATASET_PATH)
    env.setdefault("OUTPUT_DIR", str(OUTPUT_DIR))
    return {key: value for key, value in env.items() if key in set(RUN_ENV_KEYS) or key in os.environ}


async def collect_output(stream: asyncio.StreamReader) -> None:
    while True:
        line = await stream.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").rstrip()
        logger.info("benchmark-runner %s", text)
        state.output_tail.append(text)
        state.output_tail = state.output_tail[-80:]


async def run_benchmark_process() -> None:
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(
            "starting benchmark process script=%s dataset=%s scenarios=%s cloud_url=%s edge_url=%s",
            BENCHMARK_SCRIPT,
            DATASET_PATH,
            os.getenv("BENCHMARK_SCENARIOS", ""),
            os.getenv("CLOUD_URL", ""),
            os.getenv("EDGE_URL", ""),
        )
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(BENCHMARK_SCRIPT),
            cwd="/app",
            env=benchmark_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        state.process = process
        if process.stdout is not None:
            await collect_output(process.stdout)
        state.return_code = await process.wait()
        state.finished_at = utc_now()
        state.status = "completed" if state.return_code == 0 else "failed"
        if state.return_code != 0:
            state.error = f"Benchmark exited with code {state.return_code}"
        logger.info("benchmark process finished status=%s return_code=%s", state.status, state.return_code)
    except Exception as exc:
        state.return_code = None
        state.finished_at = utc_now()
        state.status = "failed"
        state.error = str(exc)
        logger.exception("benchmark process failed")
    finally:
        state.process = None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status")
async def status() -> dict[str, Any]:
    return state.snapshot()


@app.post("/run")
async def run(request: RunRequest) -> dict[str, Any]:
    async with state.lock:
        if state.status == "running":
            if not request.force:
                raise HTTPException(status_code=409, detail="Benchmark is already running")
            if state.process is not None:
                state.process.terminate()
                await state.process.wait()

        if not BENCHMARK_SCRIPT.exists():
            raise HTTPException(status_code=500, detail=f"Benchmark script not found: {BENCHMARK_SCRIPT}")

        state.status = "running"
        state.started_at = utc_now()
        state.finished_at = None
        state.return_code = None
        state.error = None
        state.output_tail = []
        logger.info("benchmark run requested force=%s", request.force)
        asyncio.create_task(run_benchmark_process())
        return state.snapshot()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, log_level="info")
