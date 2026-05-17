# Lance l'environnement de développement complet (sans Docker).
#
# Usage :
#   powershell -File dev.ps1                  # corpus "calames" par défaut
#   powershell -File dev.ps1 -Corpus test     # corpus "test"

param(
    [string]$Corpus = "calames"
)

$root = $PSScriptRoot

# --- Secrets locaux (LLM, etc.) ---
$secretsFile = "$root\secrets.ps1"
if (Test-Path $secretsFile) { . $secretsFile }

$llmBaseUrl = $env:NL_LLM_BASE_URL
$llmApiKey  = $env:NL_LLM_API_KEY
$llmModel   = $env:NL_LLM_MODEL

# --- Lecture de la configuration du corpus ---
$config = Get-Content "$root\corpora.json" | ConvertFrom-Json
$corpusConfig = $config.$Corpus
if (-not $corpusConfig) {
    $available = ($config.PSObject.Properties.Name) -join ", "
    Write-Error "Corpus '$Corpus' inconnu. Corpus disponibles : $available"
    exit 1
}

$index   = $corpusConfig.index
$dataDir = $corpusConfig.data_dir

Write-Host ""
Write-Host "Corpus     : $Corpus"
Write-Host "Index      : $index"
Write-Host "Data dir   : $dataDir"
Write-Host ""

# --- MeiliSearch ---
$meili = Join-Path $root "meilisearch.exe"
if (-not (Test-Path $meili)) {
    Write-Error "meilisearch.exe introuvable à la racine du projet."
    exit 1
}
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$meili' --master-key changeme" `
    -WorkingDirectory $root

# --- API FastAPI ---
$port = 8000
$existing = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
            Where-Object State -eq 'Listen' |
            Select-Object -ExpandProperty OwningProcess -First 1
if ($existing) {
    Stop-Process -Id $existing -Force
    Start-Sleep -Milliseconds 500
}
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "`$env:MEILI_HOST='http://localhost:7700'; `$env:MEILI_KEY='changeme'; `$env:MEILI_INDEX='$index'; `$env:DATA_DIR='$dataDir'; `$env:NL_LLM_BASE_URL='$llmBaseUrl'; `$env:NL_LLM_API_KEY='$llmApiKey'; `$env:NL_LLM_MODEL='$llmModel'; cd '$root\backend'; python -m uvicorn api.main:app --reload --port $port" `
    -WorkingDirectory "$root\backend"

# --- Frontend Vite ---
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev" `
    -WorkingDirectory "$root\frontend"

Write-Host "Environnement de développement démarré :"
Write-Host "  MeiliSearch : http://localhost:7700"
Write-Host "  API         : http://localhost:$port  (corpus: $Corpus)"
Write-Host "  Frontend    : http://localhost:5173"
