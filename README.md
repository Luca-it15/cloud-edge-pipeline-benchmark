# Benchmark clinico Cloud vs Edge

Questo progetto confronta due pipeline di monitoraggio pazienti:

- **Cloud pipeline**: il campione wearable del paziente viene inviato a Google Cloud Run, che valida i dati e restituisce eventuali alert.
- **Edge pipeline HTTP**: lo stesso campione viene inviato a un edge server locale senza TLS.
- **Edge pipeline TLS**: lo stesso campione viene inviato a un edge server locale via HTTPS/TLS.

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

Vengono eseguiti:

- validazione schema;
- validazione del campione wearable piu' recente;
- controllo soglie fuori norma per frequenza cardiaca, pressione sistolica, frequenza respiratoria, SpO2, temperatura e glicemia;
- livello alert: `low`, `medium`, `high`, `critical`;
- azione raccomandata;
- alert se almeno un valore e' fuori norma oppure il payload non e' valido.

## Pipeline cloud nel dettaglio

La pipeline cloud riceve il campione wearable e restituisce l'alert alla dashboard/runner.

```text
dashboard / benchmark runner
  -> Cloud Run /process
  -> validazione payload wearable
  -> controllo soglie fuori norma
  -> alert generation
  -> risposta alla dashboard/runner
```

Informazioni inviate al cloud per ogni campione:

```text
demografia completa
reparto e letto
diagnosi
comorbidita'
farmaci
serie dei parametri vitali wearable
```

Informazioni salvate dal cloud:

```text
full patient record
full vital time-series
risk assessment
triage recommendation
```

## Pipeline edge nel dettaglio

La pipeline edge riceve lo stesso campione del cloud e processa localmente i dati senza sincronizzare verso il cloud durante la misura. Esistono due varianti identiche come logica e risorse: HTTP e HTTPS/TLS.

```text
dashboard / benchmark runner
  -> edge-api /process
  -> validazione payload wearable
  -> controllo soglie fuori norma
  -> alert locale
  -> risposta alla dashboard/runner
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

Nel benchmark attuale l'edge non sincronizza dati verso Google Cloud Run. Il confronto misura la latenza end-to-end richiesta/risposta tra dashboard/runner e tre destinazioni: Cloud Run, edge HTTP, edge TLS.

## Scenari benchmark

Per ogni paziente vengono eseguiti tre scenari, ripetuti 3 volte per ridurre il rumore delle singole misure:

```text
cloud
edge
edge_tls
```

- `cloud`: processing completo su Google Cloud Run.
- `edge`: processing locale edge via HTTP.
- `edge_tls`: processing locale edge via HTTPS/TLS.

## Avvio

Avvio guidato da Windows:

```text
doppio click su start_benchmark.bat
```

Lo script controlla Docker, configura Cloud Run se manca `.env.gcp`, avvia lo stack e mostra gli URL locali.

```powershell
.\scripts\deploy-cloud-run.ps1 -ProjectId benchmark-edge-cloud -Region europe-west8
docker compose --env-file .env.gcp up --build
```

Servizi:

```text
Cloud API:             Google Cloud Run URL in .env.gcp
Edge API locale:       http://localhost:8001/docs
Edge API TLS locale:   https://localhost:8444/docs
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
docker compose --env-file .env.gcp run --rm benchmark
```

Output:

```text
results/results.csv
results/summary.json
results/patient_results.json
```

`patient_results.json` alimenta la dashboard ospedaliera.

## Pipeline cloud su Google Cloud Run

Il benchmark usa Google Cloud Run come unica pipeline cloud. Docker avvia solo l'edge locale, Prometheus, Grafana, dashboard e benchmark runner.

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

Lo script usa `-MinInstances 1` come default per tenere Cloud Run caldo durante il benchmark e rendere il confronto edge/cloud piu' stabile.

Lo script:

- abilita le API necessarie;
- crea il repository Docker in Artifact Registry se manca;
- builda `services/pipeline_api`;
- deploya `benchmark-cloud-api` su Cloud Run;
- genera `.env.gcp` e `prometheus/prometheus.gcp.yml`.

Il compose imposta `DATASET_REPEATS=3`, quindi il benchmark produce 180 richieste totali: 20 pazienti x 3 scenari x 3 ripetizioni.

Avvio dello stack:

```powershell
docker compose --env-file .env.gcp up --build
```

Lancio benchmark:

```powershell
docker compose --env-file .env.gcp run --rm benchmark
```

In questa modalita' vengono eseguiti:

```text
cloud
edge
edge_tls
```

Lo scenario `edge_tls` usa TLS reale terminato dall'edge locale. Su Cloud Run l'HTTPS pubblico e' terminato dalla piattaforma Google Cloud.

Se il servizio Cloud Run e' gia' deployato e vuoi solo riconfigurare l'endpoint locale:

```powershell
.\scripts\configure-gcp-hybrid.ps1 -CloudRunUrl https://URL-CLOUD-RUN -ProjectId benchmark-edge-cloud -Region europe-west8
```

Cloud Run non chiama direttamente la dashboard locale a fine pipeline: la dashboard/runner invia il campione a Cloud Run e riceve la risposta HTTP con l'alert. Un callback Cloud Run -> PC richiederebbe un endpoint pubblico o un tunnel, e introdurrebbe latenza esterna non utile per questo benchmark.

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
- confronto cloud/edge per latenza, trasporto e payload inviato al server;
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

Grafana visualizza queste metriche nel tempo. Per default Prometheus scrapa solo l'edge locale, cosi' il traffico di monitoraggio resta separato dal traffico del benchmark.

La pipeline cloud espone comunque `/metrics` su Cloud Run. Se vuoi osservare anche le metriche applicative cloud con Prometheus, usa il file generato:

```text
prometheus/prometheus.gcp.with-cloud.yml
```

Avvio con scrape cloud abilitato:

```powershell
docker compose --env-file .env.gcp -f docker-compose.yml -f docker-compose.cloud-metrics.yml up --build
```

Nota: uno scrape Prometheus verso Cloud Run e' una richiesta HTTP reale, quindi puo' alterare il traffico osservato dal benchmark. Per metriche infrastrutturali cloud senza disturbare il traffico applicativo, usa Cloud Monitoring di Google Cloud.

## Log pipeline

I servizi emettono log JSON per rendere espliciti gli step clinici eseguiti sui dati sanitari. Nei log di Cloud Run e nei log Docker dell'edge troverai eventi `clinical_pipeline_step` con:

```text
request_received
network_uplink
transport_security
wearable_payload_validation
abnormal_threshold_check
cloud_storage
dashboard_response
```

I log includono hash pseudonimizzato del paziente, reparto, letto, diagnosi, numero di campioni vitali, campi clinici usati, payload inviato, rischio calcolato e timing per step. Non vengono stampati nome paziente o valori grezzi dei parametri vitali.

L'edge locale e' configurato come `ward-gateway-0.5vcpu-256mb` con:

```text
cpus: 0.5
mem_limit: 256m
pids_limit: 128
```

I delay `PREPROCESS_MS` e `INFERENCE_MS` sono piu' alti rispetto al cloud per simulare hardware edge meno potente.

## File principali

```text
data/patients.json                         dataset pazienti
services/pipeline_api/app/clinical.py      logica clinica
services/pipeline_api/app/main.py          API cloud/edge
services/benchmark/benchmark.py            runner benchmark
services/benchmark_api/app/main.py         API controllo benchmark
services/hospital_dashboard/app/main.py    gestionale ospedaliero
docker-compose.yml                         orchestrazione edge locale + Cloud Run
docs/cloud-edge-pipeline-benchmark-report.pdf
```

## Note sicurezza

Il traffico verso Cloud Run usa HTTPS terminato dalla piattaforma Google Cloud. Lo scenario `edge_tls` usa TLS reale sull'edge locale con certificati generati dal servizio `certgen`.

I certificati locali delle versioni precedenti restano ignorati da Git:

```text
certs/*.crt
certs/*.key
```
