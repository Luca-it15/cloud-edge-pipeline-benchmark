@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

echo.
echo ============================================
echo  Cloud vs Edge Clinical Benchmark - startup
echo ============================================
echo.

where docker >nul 2>nul
if errorlevel 1 (
  echo [ERRORE] Docker non e' installato o non e' nel PATH.
  echo Installa Docker Desktop, avvialo e riprova.
  pause
  exit /b 1
)

docker compose version >nul 2>nul
if errorlevel 1 (
  echo [ERRORE] Docker Compose non e' disponibile.
  echo Aggiorna Docker Desktop e riprova.
  pause
  exit /b 1
)

echo [1/5] Controllo Docker...
docker info >nul 2>nul
if not errorlevel 1 goto DOCKER_READY

echo Docker non sembra attivo. Provo ad avviare Docker Desktop...
if exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" goto START_DOCKER_DESKTOP

echo [ERRORE] Non trovo Docker Desktop nel percorso standard.
echo Avvialo manualmente e rilancia questo script.
pause
exit /b 1

:START_DOCKER_DESKTOP
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
set /a WAITED=0

:WAIT_DOCKER
timeout /t 5 /nobreak >nul
set /a WAITED+=5
docker info >nul 2>nul
if not errorlevel 1 goto DOCKER_READY
if !WAITED! GEQ 120 goto DOCKER_TIMEOUT
echo Attendo Docker... !WAITED!s
goto WAIT_DOCKER

:DOCKER_TIMEOUT
echo [ERRORE] Docker non e' diventato pronto entro 120 secondi.
echo Avvia Docker Desktop manualmente e riprova.
pause
exit /b 1

:DOCKER_READY
echo Docker pronto.
echo.

if exist ".env.gcp" goto ENV_READY

echo [2/5] File .env.gcp non trovato.
echo.
echo Scegli come configurare Cloud Run:
echo   1 - Deploy automatico su Google Cloud Run con gcloud
echo   2 - Uso un URL Cloud Run gia' esistente
echo   3 - Esci
echo.
set /p SETUP_CHOICE="Scelta [1/2/3]: "

if "%SETUP_CHOICE%"=="1" goto DEPLOY_CLOUD_RUN
if "%SETUP_CHOICE%"=="2" goto CONFIGURE_EXISTING
echo Uscita.
pause
exit /b 0

:DEPLOY_CLOUD_RUN
set "PROJECT_ID=benchmark-edge-cloud"
set "REGION=europe-west8"
echo.
set /p PROJECT_ID="Project ID Google Cloud [benchmark-edge-cloud]: "
if "%PROJECT_ID%"=="" set "PROJECT_ID=benchmark-edge-cloud"
set /p REGION="Regione Google Cloud [europe-west8]: "
if "%REGION%"=="" set "REGION=europe-west8"
echo.
echo Avvio deploy Cloud Run. Serve gcloud installato, autenticato e con billing attivo.
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\deploy-cloud-run.ps1" -ProjectId "%PROJECT_ID%" -Region "%REGION%"
if errorlevel 1 (
  echo [ERRORE] Deploy Cloud Run fallito.
  pause
  exit /b 1
)
goto ENV_READY

:CONFIGURE_EXISTING
echo.
set /p CLOUD_RUN_URL="Incolla URL Cloud Run HTTPS: "
if "%CLOUD_RUN_URL%"=="" (
  echo [ERRORE] URL Cloud Run vuoto.
  pause
  exit /b 1
)
set "PROJECT_ID=benchmark-edge-cloud"
set "REGION=europe-west8"
set /p PROJECT_ID="Project ID Google Cloud [benchmark-edge-cloud]: "
if "%PROJECT_ID%"=="" set "PROJECT_ID=benchmark-edge-cloud"
set /p REGION="Regione Google Cloud [europe-west8]: "
if "%REGION%"=="" set "REGION=europe-west8"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\configure-gcp-hybrid.ps1" -CloudRunUrl "%CLOUD_RUN_URL%" -ProjectId "%PROJECT_ID%" -Region "%REGION%"
if errorlevel 1 (
  echo [ERRORE] Configurazione Cloud Run fallita.
  pause
  exit /b 1
)

:ENV_READY
echo [2/5] Configurazione GCP trovata.

if exist "prometheus\prometheus.gcp.yml" goto PROM_READY

echo [3/5] Rigenero configurazione Prometheus da .env.gcp...
for /f "usebackq tokens=1,* delims==" %%A in (".env.gcp") do (
  if "%%A"=="GCP_CLOUD_URL" set "GCP_CLOUD_URL=%%B"
  if "%%A"=="GCP_PROJECT_ID" set "GCP_PROJECT_ID=%%B"
  if "%%A"=="GCP_REGION" set "GCP_REGION=%%B"
)
if "%GCP_PROJECT_ID%"=="" set "GCP_PROJECT_ID=benchmark-edge-cloud"
if "%GCP_REGION%"=="" set "GCP_REGION=europe-west8"
if "%GCP_CLOUD_URL%"=="" (
  echo [ERRORE] .env.gcp non contiene GCP_CLOUD_URL.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\configure-gcp-hybrid.ps1" -CloudRunUrl "%GCP_CLOUD_URL%" -ProjectId "%GCP_PROJECT_ID%" -Region "%GCP_REGION%"
if errorlevel 1 (
  echo [ERRORE] Rigenerazione configurazione Prometheus fallita.
  pause
  exit /b 1
)
goto PROM_DONE

:PROM_READY
echo [3/5] Configurazione Prometheus trovata.

:PROM_DONE
echo.
echo [4/5] Avvio stack Docker in background...
docker compose --env-file .env.gcp up --build -d
if errorlevel 1 (
  echo [ERRORE] Avvio stack Docker fallito.
  pause
  exit /b 1
)

echo.
echo [5/5] Stato servizi:
docker compose --env-file .env.gcp ps

echo.
echo Stack avviato.
echo.
echo URL utili:
echo   Dashboard ospedaliera: http://localhost:8080
echo   Benchmark API:         http://localhost:8090/status
echo   Edge API HTTP:         http://localhost:8001/docs
echo   Edge API TLS:          https://localhost:8444/docs
echo   Prometheus:            http://localhost:9090
echo   Grafana:               http://localhost:3000  user=admin password=admin
echo.

set /p OPEN_DASHBOARD="Aprire la dashboard nel browser? [S/N]: "
if /i "%OPEN_DASHBOARD%"=="S" start "" "http://localhost:8080"

echo.
set /p RUN_BENCHMARK="Lanciare subito il benchmark clinico? [S/N]: "
if /i "%RUN_BENCHMARK%"=="S" (
  echo.
  echo Avvio benchmark. I risultati finiranno in results\.
  docker compose --env-file .env.gcp run --rm benchmark
  if errorlevel 1 (
    echo [ERRORE] Benchmark fallito.
    pause
    exit /b 1
  )
)

echo.
echo Operazione completata.
pause
