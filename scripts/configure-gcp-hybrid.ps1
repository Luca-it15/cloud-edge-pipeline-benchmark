param(
    [Parameter(Mandatory = $true)]
    [string]$CloudRunUrl,

    [string]$ProjectId = "benchmark-edge-cloud",
    [string]$Region = "europe-west8"
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$normalizedUrl = $CloudRunUrl.TrimEnd("/")
$uri = [System.Uri]$normalizedUrl

if ($uri.Scheme -ne "https") {
    throw "CloudRunUrl must use https: $CloudRunUrl"
}

$envFile = Join-Path $root ".env.gcp"
$templateFile = Join-Path $root "prometheus\prometheus.gcp.template.yml"
$prometheusFile = Join-Path $root "prometheus\prometheus.gcp.yml"

@(
    "GCP_PROJECT_ID=$ProjectId"
    "GCP_REGION=$Region"
    "GCP_CLOUD_URL=$normalizedUrl"
    "GCP_CLOUD_HOST=$($uri.Host)"
) | Set-Content -LiteralPath $envFile -Encoding ascii

$template = Get-Content -LiteralPath $templateFile -Raw
$template.Replace("__GCP_CLOUD_HOST__", $uri.Host) |
    Set-Content -LiteralPath $prometheusFile -Encoding ascii

Write-Host "Configured hybrid benchmark:"
Write-Host "  .env.gcp"
Write-Host "  prometheus/prometheus.gcp.yml"
Write-Host ""
Write-Host "Run:"
Write-Host "  docker compose --env-file .env.gcp -f docker-compose.yml -f docker-compose.gcp.yml up --build"
Write-Host "  docker compose --env-file .env.gcp -f docker-compose.yml -f docker-compose.gcp.yml run --rm benchmark"
