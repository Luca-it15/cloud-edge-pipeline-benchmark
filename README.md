# Benchmark pipeline Cloud vs Edge

Questa demo confronta pipeline cloud ed edge con tre livelli di comunicazione:

- **plain**: HTTP senza sicurezza di trasporto.
- **simulated secure**: HTTP plain, ma con overhead applicativo simulato per TLS/HMAC/cifratura/replay check.
- **TLS reale**: HTTPS reale con CA locale self-signed e certificato client per mTLS.

Il benchmark scrive:

- `results/results.csv`: una riga per ogni richiesta.
- `results/summary.json`: statistiche aggregate per pipeline.
- metriche Prometheus esposte da tutte le API.
- dashboard Grafana gia' provisionata.

## Avvio completo

Da questa cartella:

```powershell
docker compose up --build
```

Questo comando:

1. genera certificati locali nel volume `certs/` tramite `certgen`;
2. avvia la pipeline cloud plain;
3. avvia la pipeline edge plain;
4. avvia la pipeline cloud TLS;
5. avvia la pipeline edge TLS;
6. avvia Prometheus;
7. avvia Grafana.

Servizi disponibili:

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

Nota: gli endpoint TLS richiedono certificati self-signed locali. Il browser potrebbe non aprire `/docs` senza importare la CA e il certificato client; il benchmark invece li usa automaticamente.

## Lanciare il benchmark

Con i servizi gia' attivi:

```powershell
docker compose run --rm benchmark
```

Il runner esegue, per ogni run:

```text
cloud
edge
cloud_simulated_secure
edge_simulated_secure
cloud_tls
edge_tls
```

Quindi confronta:

- cloud vs edge;
- overhead di sicurezza simulato;
- overhead TLS/mTLS reale osservato dal client;
- differenza di banda logica tra dato grezzo inviato al cloud e risultato ridotto sincronizzato dall'edge.

## Flusso delle pipeline

Pipeline cloud plain:

```text
client -> cloud-api HTTP -> network simulated -> preprocessing -> inference -> storage
```

Pipeline edge plain:

```text
client -> edge-api HTTP -> network simulated -> preprocessing -> inference -> sync result to cloud
```

Pipeline cloud TLS:

```text
client -> HTTPS/mTLS -> cloud-api-tls -> network simulated -> preprocessing -> inference -> storage
```

Pipeline edge TLS:

```text
client -> HTTPS/mTLS -> edge-api-tls -> network simulated -> preprocessing -> inference -> HTTPS/mTLS sync to cloud-api-tls
```

## Campi importanti nel CSV

Il file `results/results.csv` contiene:

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

Interpretazione:

- `client_total_ms`: latenza end-to-end vista dal client.
- `service_total_ms`: tempo misurato dentro l'API, dopo che la richiesta e' arrivata.
- `client_service_delta_ms`: differenza tra client e servizio. Nei casi TLS include handshake TLS/mTLS, setup connessione, serializzazione e overhead HTTP.
- `security_ms`: overhead applicativo simulato, usato solo nei casi `*_simulated_secure`.
- `transport_security`: `plain` oppure `tls`.
- `sync_ms`: per edge, include la sincronizzazione del risultato verso cloud.
- `payload_synced_kb`: nel cloud e' il dato grezzo; nell'edge e' il risultato ridotto.

## Configurare i benchmark

Modifica `docker-compose.yml`.

Parametri principali:

```yaml
RUNS: 30
DATA_SIZE_KB: 512
COMPLEXITY: 1.0
NETWORK_UPLINK_MS: 80
PREPROCESS_MS: 24
INFERENCE_MS: 36
STORAGE_MS: 12
```

Parametri per sicurezza simulata:

```yaml
SECURE_TLS_HANDSHAKE_MS: 18
SECURE_AUTH_MS: 4
SECURE_CRYPTO_MS_PER_MB: 7
SECURE_REPLAY_CHECK_MS: 2
SECURE_PACKET_OVERHEAD_KB: 2
```

Limiti edge:

```yaml
cpus: "1.0"
mem_limit: 512m
```

## Comandi utili

Avvio completo:

```powershell
docker compose up --build
```

Avvio in background:

```powershell
docker compose up -d --build
```

Eseguire benchmark:

```powershell
docker compose run --rm benchmark
```

Vedere stato container:

```powershell
docker compose ps
```

Vedere log:

```powershell
docker compose logs -f cloud-api edge-api cloud-api-tls edge-api-tls
```

Fermare tutto:

```powershell
docker compose down
```

Rigenerare i certificati:

```powershell
docker compose run --rm -e FORCE_REGENERATE_CERTS=1 certgen
docker compose up -d --build
```

## Sicurezza modellata

La demo ora ha due tipi di sicurezza:

- `*_simulated_secure`: misura un overhead controllato e configurabile per spiegare il costo di TLS, HMAC/token, cifratura e anti-replay.
- `*_tls`: usa HTTPS reale con certificati generati localmente. Il client verifica la CA locale e presenta un certificato client per mTLS.

Per una tesi o relazione, puoi usare `*_simulated_secure` per spiegare i singoli contributi teorici e `*_tls` per mostrare una misura reale di trasporto.
