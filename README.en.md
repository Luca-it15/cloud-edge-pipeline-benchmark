# Clinical Cloud vs Edge Benchmark

This project compares two patient-monitoring pipelines:

- **Cloud pipeline**: the complete patient record is sent to the cloud, and all processing is executed there.
- **Edge pipeline**: the record is processed close to the ward/bed and a local alert is generated, without including cloud synchronization in the measured latency.

The benchmark uses a realistic synthetic dataset of 20 patients in [data/patients.json](data/patients.json), including ward, bed, diagnosis, comorbidities, medications, and time-series vital signs.

## What Is Processed

Each patient contains:

```text
patient_id, name, age, sex
ward, bed
primary_diagnosis
comorbidities
medications
vitals[]:
  timestamp
  heart_rate
  systolic_bp
  respiratory_rate
  spo2
  temperature
  glucose
```

Clinical logic lives in:

```text
services/pipeline_api/app/clinical.py
```

It computes:

- schema validation;
- vital-sign range clamping;
- moving-average filtering on the edge;
- clinical features: latest values, averages, trends;
- vital-sign score;
- trend score;
- clinical-context score;
- risk level: `low`, `medium`, `high`, `critical`;
- recommended action;
- alert if risk is `high` or `critical`.

## Cloud Pipeline in Detail

The cloud pipeline receives the complete patient record.

```text
benchmark client
  -> cloud-api /process
  -> simulated network delay
  -> record validation
  -> vital-sign normalization
  -> feature extraction on the full time series
  -> risk scoring
  -> triage / alert
  -> full-record storage
  -> response to client
```

Information sent to the cloud:

```text
full demographics
ward and bed
diagnosis
comorbidities
medications
complete vital-sign time series
```

Information stored by the cloud:

```text
full patient record
full vital time-series
risk assessment
triage recommendation
```

## Edge Pipeline in Detail

The edge pipeline receives the patient record, processes it locally, and synchronizes only a reduced result to the cloud.

```text
benchmark client
  -> edge-api /process
  -> simulated local network delay
  -> record validation
  -> vital-sign clamping
  -> moving-average filtering
  -> local feature extraction
  -> early-warning score
  -> local alert
  -> response to client
```

Information used locally by the edge:

```text
complete patient record
complete vital-sign time series
```

Information produced by the edge:

```text
patient_id
pseudonymized patient_hash
ward
bed
latest_vitals
risk_score
risk_level
recommended_action
alert
```

In the direct edge vs cloud comparison, the edge pipeline does not send data to the cloud during the measurement. The `payload_synced_kb` field is therefore `0` for edge scenarios.

## Benchmark Scenarios

For each patient, the runner executes six scenarios:

```text
cloud
edge
cloud_simulated_secure
edge_simulated_secure
cloud_tls
edge_tls
```

- `cloud`: complete cloud processing over HTTP.
- `edge`: local edge processing over HTTP, with no cloud sync included.
- `*_simulated_secure`: adds simulated delay for TLS/HMAC/encryption/anti-replay.
- `*_tls`: uses real HTTPS/mTLS with a local CA and client certificate.

## Startup

```powershell
docker compose up --build
```

Services:

```text
Cloud API plain:       http://localhost:8000/docs
Edge API plain:        http://localhost:8001/docs
Cloud API TLS/mTLS:    https://localhost:8443/docs
Edge API TLS/mTLS:     https://localhost:8444/docs
Hospital dashboard:    http://localhost:8080
Benchmark API:         http://localhost:8090
Prometheus:            http://localhost:9090
Grafana:               http://localhost:3000
```

Grafana:

```text
user: admin
password: admin
```

## Run the Clinical Benchmark

```powershell
docker compose run --rm benchmark
```

Output:

```text
results/results.csv
results/summary.json
results/patient_results.json
```

`patient_results.json` feeds the hospital dashboard.

## Hybrid Benchmark with Google Cloud Run

To make the benchmark closer to a real deployment, you can deploy the cloud service to Google Cloud Run while keeping the edge service, Prometheus, Grafana, dashboard, and benchmark runner local.

Recommended configuration:

```text
PROJECT_ID=benchmark-edge-cloud
REGION=europe-west8
SERVICE=benchmark-cloud-api
```

Prerequisites:

```text
gcloud installed and authenticated
billing enabled on the Google Cloud project
permissions for Cloud Run, Cloud Build, and Artifact Registry
```

Deploy the cloud container:

```powershell
.\scripts\deploy-cloud-run.ps1 -ProjectId benchmark-edge-cloud -Region europe-west8
```

The script:

- enables the required APIs;
- creates the Docker repository in Artifact Registry if missing;
- builds `services/pipeline_api`;
- deploys `benchmark-cloud-api` to Cloud Run;
- generates `.env.gcp` and `prometheus/prometheus.gcp.yml` for the hybrid benchmark.

Start the hybrid stack:

```powershell
docker compose --env-file .env.gcp -f docker-compose.yml -f docker-compose.gcp.yml up --build
```

Run the hybrid benchmark:

```powershell
docker compose --env-file .env.gcp -f docker-compose.yml -f docker-compose.gcp.yml run --rm benchmark
```

This mode runs:

```text
cloud
edge
cloud_simulated_secure
edge_simulated_secure
```

The `cloud_tls` and `edge_tls` scenarios remain part of the local profile because they use mTLS terminated inside the containers. On Cloud Run, public HTTPS is terminated by the platform; for real mTLS on Google Cloud, use an Application Load Balancer with mTLS or move the deployment to GKE/Compute Engine.

If the Cloud Run service is already deployed and you only need to configure the local endpoint:

```powershell
.\scripts\configure-gcp-hybrid.ps1 -CloudRunUrl https://CLOUD-RUN-URL -ProjectId benchmark-edge-cloud -Region europe-west8
```

## Hospital Dashboard

Open:

```text
http://localhost:8080
```

The dashboard shows:

- patient worklist by ward;
- risk level;
- clinical score;
- latest vital signs;
- diagnosis, medications, comorbidities;
- recommended action;
- cloud/edge/TLS comparison for latency, sync time, and cloud payload;
- ward load and active alerts.

The dashboard can also start the benchmark through the:

```text
Run benchmark
```

button. The button calls the `benchmark-api` service, which runs the benchmark runner in the background and updates:

```text
results/results.csv
results/summary.json
results/patient_results.json
```

When the status returns to `completed`, the dashboard reloads the results automatically.

Control endpoints:

```text
POST http://localhost:8090/run
GET  http://localhost:8090/status
```

## Prometheus and Grafana

Prometheus collects runtime metrics from `/metrics`:

```text
pipeline_requests_total
pipeline_total_latency_ms
pipeline_stage_latency_ms
pipeline_payload_size_kb
pipeline_in_flight_requests
```

Grafana visualizes these metrics over time. The hospital dashboard visualizes clinical benchmark results.

## Main Files

```text
data/patients.json                         patient dataset
services/pipeline_api/app/clinical.py      clinical logic
services/pipeline_api/app/main.py          cloud/edge API
services/benchmark/benchmark.py            benchmark runner
services/benchmark_api/app/main.py         benchmark control API
services/hospital_dashboard/app/main.py    hospital dashboard
docker-compose.yml                         orchestration
docs/cloud-edge-pipeline-benchmark-report.pdf
```

## Security Notes

TLS certificates are generated locally by `certgen` and ignored by Git:

```text
certs/*.crt
certs/*.key
```

They are suitable for local benchmarking, not production.
