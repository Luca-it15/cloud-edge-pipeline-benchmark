# Cloud vs Edge Pipeline Benchmark

This demo compares cloud and edge pipelines with three communication modes:

- **plain**: HTTP without transport security.
- **simulated secure**: plain HTTP plus configurable application-level overhead for TLS/HMAC/encryption/replay checks.
- **real TLS**: real HTTPS with a local self-signed CA and a client certificate for mTLS.

The benchmark writes:

- `results/results.csv`: one row per request.
- `results/summary.json`: aggregated statistics per pipeline.
- Prometheus metrics from all API services.
- a pre-provisioned Grafana dashboard.

## Full Startup

From this folder:

```powershell
docker compose up --build
```

This command:

1. generates local certificates in `certs/` through the `certgen` service;
2. starts the plain cloud pipeline;
3. starts the plain edge pipeline;
4. starts the TLS cloud pipeline;
5. starts the TLS edge pipeline;
6. starts Prometheus;
7. starts Grafana.

Available services:

```text
Cloud API plain:      http://localhost:8000/docs
Edge API plain:       http://localhost:8001/docs
Cloud API TLS/mTLS:   https://localhost:8443/docs
Edge API TLS/mTLS:    https://localhost:8444/docs
Prometheus:           http://localhost:9090
Grafana:              http://localhost:3000
```

Grafana:

```text
user: admin
password: admin
```

Note: TLS endpoints use local self-signed certificates. A browser may not open `/docs` unless you import the local CA and client certificate. The benchmark uses them automatically.

## Run the Benchmark

With the services already running:

```powershell
docker compose run --rm benchmark
```

For each run, the runner executes:

```text
cloud
edge
cloud_simulated_secure
edge_simulated_secure
cloud_tls
edge_tls
```

This lets you compare:

- cloud vs edge;
- simulated security overhead;
- real TLS/mTLS overhead observed by the client;
- logical bandwidth difference between raw data sent to cloud and reduced result synced by edge.

## Pipeline Flow

Plain cloud pipeline:

```text
client -> cloud-api HTTP -> simulated network -> preprocessing -> inference -> storage
```

Plain edge pipeline:

```text
client -> edge-api HTTP -> simulated network -> preprocessing -> inference -> sync result to cloud
```

TLS cloud pipeline:

```text
client -> HTTPS/mTLS -> cloud-api-tls -> simulated network -> preprocessing -> inference -> storage
```

TLS edge pipeline:

```text
client -> HTTPS/mTLS -> edge-api-tls -> simulated network -> preprocessing -> inference -> HTTPS/mTLS sync to cloud-api-tls
```

## Important CSV Fields

`results/results.csv` contains:

```text
pipeline
client_total_ms
service_total_ms
client_service_delta_ms
security_profile
transport_security
network_ms
security_ms
tls_handshake_ms
auth_ms
crypto_ms
replay_check_ms
preprocess_ms
inference_ms
storage_ms
sync_ms
payload_sent_kb
payload_synced_kb
security_overhead_kb
```

How to read them:

- `client_total_ms`: end-to-end latency observed by the client.
- `service_total_ms`: time measured inside the API after the request has arrived.
- `client_service_delta_ms`: difference between client and service timing. In TLS cases, it includes TLS/mTLS handshake, connection setup, serialization, and HTTP overhead.
- `security_ms`: simulated application-level security overhead, used only by `*_simulated_secure`.
- `transport_security`: `plain` or `tls`.
- `sync_ms`: for edge, includes result synchronization to cloud.
- `payload_synced_kb`: raw payload for cloud, reduced result for edge.

## Configure the Benchmark

Edit `docker-compose.yml`.

Main parameters:

```yaml
RUNS: 30
DATA_SIZE_KB: 512
COMPLEXITY: 1.0
NETWORK_UPLINK_MS: 80
PREPROCESS_MS: 24
INFERENCE_MS: 36
STORAGE_MS: 12
```

Simulated security parameters:

```yaml
SECURE_TLS_HANDSHAKE_MS: 18
SECURE_AUTH_MS: 4
SECURE_CRYPTO_MS_PER_MB: 7
SECURE_REPLAY_CHECK_MS: 2
SECURE_PACKET_OVERHEAD_KB: 2
```

Edge limits:

```yaml
cpus: "1.0"
mem_limit: 512m
```

## Useful Commands

Full startup:

```powershell
docker compose up --build
```

Background startup:

```powershell
docker compose up -d --build
```

Run benchmark:

```powershell
docker compose run --rm benchmark
```

Check containers:

```powershell
docker compose ps
```

View logs:

```powershell
docker compose logs -f cloud-api edge-api cloud-api-tls edge-api-tls
```

Stop everything:

```powershell
docker compose down
```

Regenerate certificates:

```powershell
docker compose run --rm -e FORCE_REGENERATE_CERTS=1 certgen
docker compose up -d --build
```

## Security Model

The demo now includes two security views:

- `*_simulated_secure`: controlled, configurable overhead for explaining the cost of TLS, HMAC/token checks, encryption, and anti-replay protection.
- `*_tls`: real HTTPS using locally generated certificates. The client verifies the local CA and presents a client certificate for mTLS.

For a thesis or report, use `*_simulated_secure` to explain theoretical stage-level cost and `*_tls` to show a real transport-level measurement.
