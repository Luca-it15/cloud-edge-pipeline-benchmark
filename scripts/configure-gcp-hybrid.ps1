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
$cloudMetricsTemplateFile = Join-Path $root "prometheus\prometheus.gcp.with-cloud.template.yml"
$prometheusFile = Join-Path $root "prometheus\prometheus.gcp.yml"
$cloudMetricsPrometheusFile = Join-Path $root "prometheus\prometheus.gcp.with-cloud.yml"

@(
    "GCP_PROJECT_ID=$ProjectId"
    "GCP_REGION=$Region"
    "GCP_CLOUD_URL=$normalizedUrl"
    "GCP_CLOUD_HOST=$($uri.Host)"
) | Set-Content -LiteralPath $envFile -Encoding ascii

$template = Get-Content -LiteralPath $templateFile -Raw
$template.Replace("__GCP_CLOUD_HOST__", $uri.Host) |
    Set-Content -LiteralPath $prometheusFile -Encoding ascii

$cloudMetricsTemplate = Get-Content -LiteralPath $cloudMetricsTemplateFile -Raw
$cloudMetricsTemplate.Replace("__GCP_CLOUD_HOST__", $uri.Host) |
    Set-Content -LiteralPath $cloudMetricsPrometheusFile -Encoding ascii

Write-Host "Configured hybrid benchmark:"
Write-Host "  .env.gcp"
Write-Host "  prometheus/prometheus.gcp.yml"
Write-Host "  prometheus/prometheus.gcp.with-cloud.yml"
Write-Host ""
Write-Host "Note: prometheus.gcp.yml does not scrape Cloud Run, so monitoring traffic stays separate from benchmark traffic."
Write-Host "Use docker-compose.cloud-metrics.yml only when you explicitly want Prometheus to scrape cloud /metrics."
Write-Host ""
Write-Host "Run:"
Write-Host "  docker compose --env-file .env.gcp up --build"
Write-Host "  docker compose --env-file .env.gcp run --rm benchmark"
