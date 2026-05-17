# Tue le process sur le port 8000 s'il existe, puis relance l'API.
#
# Usage :
#   powershell -File restart-api.ps1                  # corpus "calames" par défaut
#   powershell -File restart-api.ps1 -Corpus test

param(
    [string]$Corpus = "calames"
)

$root = $PSScriptRoot

# --- Secrets locaux (LLM, etc.) ---
$secretsFile = "$root\secrets.ps1"
if (Test-Path $secretsFile) { . $secretsFile }

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

Write-Host "Corpus : $Corpus  |  Index : $index"

# --- Arrêt du process existant ---
$port = 8000
$existingPid = (Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
        Where-Object State -eq 'Listen' |
        Select-Object -ExpandProperty OwningProcess -First 1)

if ($existingPid) {
    Stop-Process -Id $existingPid -Force
    Write-Host "Process $existingPid (port $port) arrêté."
    Start-Sleep -Milliseconds 500
}

# --- Démarrage ---
Set-Location "$root\backend"

$env:MEILI_HOST  = "http://localhost:7700"
$env:MEILI_KEY   = "changeme"
$env:MEILI_INDEX = $index
$env:DATA_DIR    = $dataDir

python -m uvicorn api.main:app --reload --port $port
