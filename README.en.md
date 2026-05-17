# Clinical Cloud vs Edge Benchmark

This project compares two patient-monitoring pipelines:

- **Cloud pipeline**: the patient wearable sample is sent to Google Cloud Run, which validates the data and returns any alert.
- **Edge pipeline HTTP**: the same sample is sent to a local edge server without TLS.
- **Edge pipeline TLS**: the same sample is sent to a local edge server over HTTPS/TLS.

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

It executes:

- schema validation;
- validation of the latest wearable sample;
- threshold checks for heart rate, systolic blood pressure, respiratory rate, SpO2, temperature, and glucose;
- alert level: `low`, `medium`, `high`, `critical`;
- recommended action;
- alert if at least one value is out of range or the payload is invalid.

## Cloud Pipeline in Detail

The cloud pipeline receives the wearable sample and returns the alert to the dashboard/runner.

```text
dashboard / benchmark runner
  -> Cloud Run /process
  -> wearable payload validation
  -> out-of-range threshold checks
  -> alert generation
  -> response to dashboard/runner
```

Information sent to the cloud for each sample:

```text
full demographics
ward and bed
diagnosis
comorbidities
medications
wearable vital-sign series
```

Information stored by the cloud:

```text
full patient record
full vital time-series
risk assessment
triage recommendation
```

## Edge Pipeline in Detail

The edge pipeline receives the same sample as the cloud and processes it locally without synchronizing to the cloud during measurement. There are two variants with identical logic and resources: HTTP and HTTPS/TLS.

```text
dashboard / benchmark runner
  -> edge-api /process
  -> wearable payload validation
  -> out-of-range threshold checks
  -> local alert
  -> response to dashboard/runner
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

In the current benchmark, the edge does not synchronize data to Google Cloud Run. The comparison measures end-to-end request/response latency between the dashboard/runner and three destinations: Cloud Run, edge HTTP, and edge TLS.

## Benchmark Scenarios

For each patient, the runner executes three scenarios, repeated 3 times to reduce single-sample noise:

```text
cloud
edge
edge_tls
```

- `cloud`: complete processing on Google Cloud Run.
- `edge`: local edge processing over HTTP.
- `edge_tls`: local edge processing over HTTPS/TLS.

## Startup

```powershell
.\scripts\deploy-cloud-run.ps1 -ProjectId benchmark-edge-cloud -Region europe-west8
docker compose --env-file .env.gcp up --build
```

Services:

```text
Cloud API:             Google Cloud Run URL in .env.gcp
Local Edge API:        http://localhost:8001/docs
Local Edge TLS API:    https://localhost:8444/docs
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
docker compose --env-file .env.gcp run --rm benchmark
```

Output:

```text
results/results.csv
results/summary.json
results/patient_results.json
```

`patient_results.json` feeds the hospital dashboard.

## Cloud Pipeline on Google Cloud Run

The benchmark uses Google Cloud Run as the only cloud pipeline. Docker starts only the local edge, Prometheus, Grafana, dashboard, and benchmark runner.

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

The script uses `-MinInstances 1` by default to keep Cloud Run warm during the benchmark and make the edge/cloud comparison more stable. To measure cold start, use:

```powershell
.\scripts\deploy-cloud-run.ps1 -ProjectId benchmark-edge-cloud -Region europe-west8 -MinInstances 0
```

Or, if the service is already deployed:

```powershell
gcloud run services update benchmark-cloud-api --region europe-west8 --min-instances 0
gcloud run services update benchmark-cloud-api --region europe-west8 --min-instances 1
```

The script:

- enables the required APIs;
- creates the Docker repository in Artifact Registry if missing;
- builds `services/pipeline_api`;
- deploys `benchmark-cloud-api` to Cloud Run;
- generates `.env.gcp` and `prometheus/prometheus.gcp.yml`.

The compose file sets `DATASET_REPEATS=3`, so the benchmark produces 180 total requests: 20 patients x 3 scenarios x 3 repeats.

Start the stack:

```powershell
docker compose --env-file .env.gcp up --build
```

Run the benchmark:

```powershell
docker compose --env-file .env.gcp run --rm benchmark
```

This mode runs:

```text
cloud
edge
edge_tls
```

The `edge_tls` scenario uses real TLS terminated by the local edge service. On Cloud Run, public HTTPS is terminated by the Google Cloud platform.

If the Cloud Run service is already deployed and you only need to configure the local endpoint:

```powershell
.\scripts\configure-gcp-hybrid.ps1 -CloudRunUrl https://CLOUD-RUN-URL -ProjectId benchmark-edge-cloud -Region europe-west8
```

Cloud Run does not call the local dashboard directly when the pipeline finishes: the dashboard/runner sends the sample to Cloud Run and receives the HTTP response with the alert. A Cloud Run -> PC callback would require a public endpoint or tunnel and would add external latency that is not useful for this benchmark.

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
- cloud/edge comparison for latency, transport, and payload sent to the server;
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
pipeline_process_started_at_seconds
pipeline_cold_start_requests_total
```

Grafana visualizes these metrics over time. By default, Prometheus scrapes only the local edge, so it does not wake Cloud Run before the benchmark and does not distort cold-start measurement.

The cloud pipeline still exposes `/metrics` on Cloud Run. If you explicitly want Prometheus to observe cloud application metrics too, use the generated file:

```text
prometheus/prometheus.gcp.with-cloud.yml
```

Start with cloud scraping enabled:

```powershell
docker compose --env-file .env.gcp -f docker-compose.yml -f docker-compose.cloud-metrics.yml up --build
```

Note: a Prometheus scrape against Cloud Run is a real HTTP request, so it can cold-start an instance or keep it warm. To measure cold start, do not enable cloud scraping before running the benchmark. For cloud infrastructure metrics without disturbing application traffic, use Google Cloud Monitoring.

## Pipeline Logs

The services emit JSON logs that make the clinical steps on health data explicit. In Cloud Run logs and local edge Docker logs, look for `clinical_pipeline_step` events with:

```text
request_received
network_uplink
transport_security
wearable_payload_validation
abnormal_threshold_check
cloud_storage
dashboard_response
```

The logs include the pseudonymized patient hash, ward, bed, diagnosis, vital-sample count, clinical fields used, sent payload, computed risk, and per-step timings. Patient names and raw vital-sign values are not printed.

The first `/process` handled by each instance is marked with `cold_start_candidate=true` and increments `pipeline_cold_start_requests_total`. If Cloud Run is configured with `min-instances=0` and is not woken by Prometheus or other requests, the first cloud sample in the benchmark includes cold-start latency.

The local edge is configured as `ward-gateway-0.5vcpu-256mb` with:

```text
cpus: 0.5
mem_limit: 256m
pids_limit: 128
```

`PREPROCESS_MS` and `INFERENCE_MS` are higher than the cloud settings to simulate less powerful edge hardware.

## Main Files

```text
data/patients.json                         patient dataset
services/pipeline_api/app/clinical.py      clinical logic
services/pipeline_api/app/main.py          cloud/edge API
services/benchmark/benchmark.py            benchmark runner
services/benchmark_api/app/main.py         benchmark control API
services/hospital_dashboard/app/main.py    hospital dashboard
docker-compose.yml                         local edge + Cloud Run orchestration
docs/cloud-edge-pipeline-benchmark-report.pdf
```

## Security Notes

Traffic to Cloud Run uses HTTPS terminated by the Google Cloud platform. The `edge_tls` scenario uses real TLS on the local edge service with certificates generated by `certgen`.

Local certificates from earlier versions remain ignored by Git:

```text
certs/*.crt
certs/*.key
```
