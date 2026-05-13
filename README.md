# Benchmark clinico Cloud vs Edge

Questo progetto confronta due pipeline di monitoraggio pazienti:

- **Cloud pipeline**: il record clinico completo del paziente viene inviato al cloud, dove vengono eseguiti tutti i processamenti.
- **Edge pipeline**: il record viene processato vicino al letto/reparto e viene generato un alert locale, senza includere sincronizzazione cloud nella latenza misurata.

Il benchmark usa un dataset fittizio ma realistico di 20 pazienti in [data/patients.json](data/patients.json), con reparto, letto, diagnosi, comorbidita', farmaci e serie temporale di parametri vitali.

## Cosa viene processato

Ogni paziente contiene:

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

La logica clinica e' in:

```text
services/pipeline_api/app/clinical.py
```

Vengono calcolati:

- validazione schema;
- pulizia/range clamping dei parametri vitali;
- filtro moving average sull'edge;
- feature cliniche: ultimo valore, medie, trend;
- score vitali;
- score trend;
- score contesto clinico;
- livello di rischio: `low`, `medium`, `high`, `critical`;
- azione raccomandata;
- alert se rischio `high` o `critical`.

## Pipeline cloud nel dettaglio

La pipeline cloud riceve il record completo del paziente.

```text
benchmark client
  -> cloud-api /process
  -> network delay simulato
  -> validazione record
  -> normalizzazione parametri vitali
  -> feature extraction su tutta la serie temporale
  -> risk scoring
  -> triage / alert
  -> storage del record completo
  -> risposta al client
```

Informazioni inviate al cloud:

```text
demografia completa
reparto e letto
diagnosi
comorbidita'
farmaci
serie completa dei parametri vitali
```

Informazioni salvate dal cloud:

```text
full patient record
full vital time-series
risk assessment
triage recommendation
```

## Pipeline edge nel dettaglio

La pipeline edge riceve il record del paziente, ma processa localmente i dati e sincronizza al cloud solo un risultato ridotto.

```text
benchmark client
  -> edge-api /process
  -> network delay locale simulato
  -> validazione record
  -> clamping parametri vitali
  -> filtro moving average
  -> feature extraction locale
  -> early warning score
  -> alert locale
  -> risposta al client
```

Informazioni usate localmente dall'edge:

```text
record completo del paziente
serie completa dei parametri vitali
```

Informazioni prodotte dall'edge:

```text
patient_id
patient_hash pseudonimizzato
ward
bed
latest_vitals
risk_score
risk_level
recommended_action
alert
```

Nel confronto diretto edge vs cloud la pipeline edge non invia dati al cloud durante la misurazione. Il campo `payload_synced_kb` resta quindi a `0` per gli scenari edge.

## Scenari benchmark

Per ogni paziente vengono eseguiti sei scenari:

```text
cloud
edge
cloud_simulated_secure
edge_simulated_secure
cloud_tls
edge_tls
```

- `cloud`: processing completo in cloud via HTTP.
- `edge`: processing locale edge via HTTP, senza sync cloud incluso.
- `*_simulated_secure`: aggiunge delay simulato per TLS/HMAC/cifratura/anti-replay.
- `*_tls`: usa HTTPS/mTLS reale con CA locale e certificato client.

## Avvio

```powershell
docker compose up --build
```

Servizi:

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

## Lanciare il benchmark clinico

```powershell
docker compose run --rm benchmark
```

Output:

```text
results/results.csv
results/summary.json
results/patient_results.json
```

`patient_results.json` alimenta la dashboard ospedaliera.

## Benchmark ibrido con Google Cloud Run

Per avvicinare il benchmark a uno scenario reale, puoi deployare il servizio cloud su Google Cloud Run e lasciare in locale l'edge, Prometheus, Grafana, dashboard e benchmark runner.

Configurazione consigliata:

```text
PROJECT_ID=benchmark-edge-cloud
REGION=europe-west8
SERVICE=benchmark-cloud-api
```

Prerequisiti:

```text
gcloud installato e autenticato
billing attivo sul progetto Google Cloud
permessi per Cloud Run, Cloud Build e Artifact Registry
```

Deploy del container cloud:

```powershell
.\scripts\deploy-cloud-run.ps1 -ProjectId benchmark-edge-cloud -Region europe-west8
```

Lo script:

- abilita le API necessarie;
- crea il repository Docker in Artifact Registry se manca;
- builda `services/pipeline_api`;
- deploya `benchmark-cloud-api` su Cloud Run;
- genera `.env.gcp` e `prometheus/prometheus.gcp.yml` per il benchmark ibrido.

Avvio dello scenario ibrido:

```powershell
docker compose --env-file .env.gcp -f docker-compose.yml -f docker-compose.gcp.yml up --build
```

Lancio benchmark ibrido:

```powershell
docker compose --env-file .env.gcp -f docker-compose.yml -f docker-compose.gcp.yml run --rm benchmark
```

In questa modalita' vengono eseguiti:

```text
cloud
edge
cloud_simulated_secure
edge_simulated_secure
```

Gli scenari `cloud_tls` ed `edge_tls` restano nel profilo locale perche' usano mTLS terminato dentro i container. Su Cloud Run l'HTTPS pubblico e' terminato dalla piattaforma; per mTLS reale su Google Cloud conviene aggiungere un Application Load Balancer con mTLS oppure passare a GKE/Compute Engine.

Se il servizio Cloud Run e' gia' deployato e vuoi solo riconfigurare l'endpoint locale:

```powershell
.\scripts\configure-gcp-hybrid.ps1 -CloudRunUrl https://URL-CLOUD-RUN -ProjectId benchmark-edge-cloud -Region europe-west8
```

## Dashboard ospedaliera

Apri:

```text
http://localhost:8080
```

La dashboard mostra:

- lista pazienti per reparto;
- livello di rischio;
- score clinico;
- parametri vitali piu' recenti;
- diagnosi, farmaci, comorbidita';
- azione raccomandata;
- confronto cloud/edge/TLS per latenza, sync e payload inviato al cloud;
- carico per reparto e alert attivi.

La dashboard puo' anche avviare il benchmark tramite il pulsante:

```text
Run benchmark
```

Il pulsante chiama il servizio `benchmark-api`, che esegue il runner benchmark in background e aggiorna:

```text
results/results.csv
results/summary.json
results/patient_results.json
```

Quando lo stato torna `completed`, la dashboard ricarica automaticamente i risultati.

Endpoint di controllo:

```text
POST http://localhost:8090/run
GET  http://localhost:8090/status
```

## Prometheus e Grafana

Prometheus raccoglie metriche runtime dagli endpoint `/metrics`:

```text
pipeline_requests_total
pipeline_total_latency_ms
pipeline_stage_latency_ms
pipeline_payload_size_kb
pipeline_in_flight_requests
```

Grafana visualizza queste metriche nel tempo. La dashboard ospedaliera invece visualizza i risultati clinici del benchmark.

## File principali

```text
data/patients.json                         dataset pazienti
services/pipeline_api/app/clinical.py      logica clinica
services/pipeline_api/app/main.py          API cloud/edge
services/benchmark/benchmark.py            runner benchmark
services/benchmark_api/app/main.py         API controllo benchmark
services/hospital_dashboard/app/main.py    gestionale ospedaliero
docker-compose.yml                         orchestrazione
docs/cloud-edge-pipeline-benchmark-report.pdf
```

## Note sicurezza

I certificati TLS sono generati localmente da `certgen` e ignorati da Git:

```text
certs/*.crt
certs/*.key
```

Sono adatti per benchmark locale, non per produzione.
