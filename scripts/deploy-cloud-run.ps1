param(
    [string]$ProjectId = "benchmark-edge-cloud",
    [string]$Region = "europe-west8",
    [string]$Repository = "benchmark",
    [string]$Service = "benchmark-cloud-api",
    [string]$ImageName = "pipeline-api",
    [string]$GcloudPath = ""
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$image = "$Region-docker.pkg.dev/$ProjectId/$Repository/$ImageName`:latest"
$defaultGcloudPath = Join-Path $env:LOCALAPPDATA "Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"

if (-not $GcloudPath) {
    $gcloudCommand = Get-Command gcloud -ErrorAction SilentlyContinue
    if ($gcloudCommand) {
        $GcloudPath = $gcloudCommand.Source
    } elseif (Test-Path -LiteralPath $defaultGcloudPath) {
        $GcloudPath = $defaultGcloudPath
    } else {
        throw "gcloud was not found in PATH or at $defaultGcloudPath. Install Google Cloud SDK or pass -GcloudPath."
    }
}

Write-Host "Using project $ProjectId in $Region"
& $GcloudPath config set project $ProjectId

$activeAccount = & $GcloudPath config get-value account
Write-Host "Active gcloud account: $activeAccount"

$projectCheck = & $GcloudPath projects describe $ProjectId --format "value(projectId)" 2>$null
if ($LASTEXITCODE -ne 0 -or $projectCheck -ne $ProjectId) {
    throw "Active account '$activeAccount' cannot access project '$ProjectId'. Log in with the project owner account or grant this account Owner/Editor plus Service Usage Admin, Cloud Run Admin, Cloud Build Editor, and Artifact Registry Admin."
}

Write-Host "Enabling required APIs"
& $GcloudPath services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

Write-Host "Ensuring Artifact Registry repository exists"
$existingRepo = & $GcloudPath artifacts repositories list `
    --location $Region `
    --filter "name:$Repository" `
    --format "value(name)"
if (-not $existingRepo) {
    & $GcloudPath artifacts repositories create $Repository `
        --repository-format docker `
        --location $Region `
        --description "Benchmark containers"
}

Write-Host "Building and pushing $image"
& $GcloudPath builds submit (Join-Path $root "services\pipeline_api") --tag $image

Write-Host "Deploying Cloud Run service $Service"
& $GcloudPath run deploy $Service `
    --image $image `
    --region $Region `
    --platform managed `
    --allow-unauthenticated `
    --memory 512Mi `
    --cpu 1 `
    --concurrency 20 `
    --timeout 60 `
    --min-instances 0 `
    --set-env-vars "ROLE=cloud,SERVICE_NAME=cloud-api-gcp,TRANSPORT_SECURITY=platform_tls,NETWORK_UPLINK_MS=0,PREPROCESS_MS=24,INFERENCE_MS=36,STORAGE_MS=12,RESULT_PAYLOAD_RATIO=0.05,SECURE_TLS_HANDSHAKE_MS=18,SECURE_AUTH_MS=4,SECURE_CRYPTO_MS_PER_MB=7,SECURE_REPLAY_CHECK_MS=2,SECURE_PACKET_OVERHEAD_KB=2"

$cloudRunUrl = & $GcloudPath run services describe $Service `
    --region $Region `
    --format "value(status.url)"

Write-Host "Cloud Run URL: $cloudRunUrl"

& (Join-Path $PSScriptRoot "configure-gcp-hybrid.ps1") `
    -CloudRunUrl $cloudRunUrl `
    -ProjectId $ProjectId `
    -Region $Region
