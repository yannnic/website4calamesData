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
# data_dir : relatif à la racine du dépôt, ou absolu
$dataDir = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($root, $corpusConfig.data_dir))

Write-Host ""
Write-Host "Corpus     : $Corpus"
Write-Host "Index      : $index"
Write-Host "Data dir   : $dataDir"
Write-Host ""

# --- Elasticsearch (conteneur Docker, sécurité désactivée, données dans le volume calames_es_dev) ---
& "$root\es-dev.ps1"
if ($LASTEXITCODE -ne 0) { exit 1 }

# --- API FastAPI ---
$port = 8000
$existing = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
            Where-Object State -eq 'Listen' |
            Select-Object -ExpandProperty OwningProcess -First 1
if ($existing) {
    # /T : arrête aussi le worker lancé par --reload (sinon il reste orphelin et sert encore le port)
    taskkill /T /F /PID $existing *> $null
    Start-Sleep -Milliseconds 500
}
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "`$env:ES_HOST='http://localhost:9200'; `$env:ES_INDEX='$index'; `$env:DATA_DIR='$dataDir'; `$env:NL_LLM_BASE_URL='$llmBaseUrl'; `$env:NL_LLM_API_KEY='$llmApiKey'; `$env:NL_LLM_MODEL='$llmModel'; cd '$root\backend'; python -m uvicorn api.main:app --reload --port $port" `
    -WorkingDirectory "$root\backend"

# --- Frontend Vite ---
foreach ($vitePort in @(5173, 5174)) {
    $vitePid = Get-NetTCPConnection -LocalPort $vitePort -State Listen -ErrorAction SilentlyContinue |
               Select-Object -ExpandProperty OwningProcess -First 1
    if ($vitePid) { taskkill /T /F /PID $vitePid *> $null }
}
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev" `
    -WorkingDirectory "$root\frontend"

Write-Host "Environnement de développement démarré :"
Write-Host "  Elasticsearch : http://localhost:9200"
Write-Host "  API         : http://localhost:$port  (corpus: $Corpus)"
Write-Host "  Frontend    : http://localhost:5173"
