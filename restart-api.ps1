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
# data_dir : relatif à la racine du dépôt, ou absolu
$dataDir = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($root, $corpusConfig.data_dir))

Write-Host "Corpus : $Corpus  |  Index : $index"

# --- Arrêt du process existant ---
$port = 8000
$existingPid = (Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
        Where-Object State -eq 'Listen' |
        Select-Object -ExpandProperty OwningProcess -First 1)

if ($existingPid) {
    # /T : arrête aussi le worker lancé par --reload (sinon il reste orphelin et sert encore le port)
    taskkill /T /F /PID $existingPid *> $null
    Write-Host "Process $existingPid (port $port) arrêté."
    Start-Sleep -Milliseconds 500
}

# --- Démarrage ---
Set-Location "$root\backend"

$env:ES_HOST  = "http://localhost:9200"
$env:ES_INDEX = $index
$env:DATA_DIR    = $dataDir

python -m uvicorn api.main:app --reload --port $port
