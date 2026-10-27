# Lance l'indexation pour un corpus donné.
#
# Usage :
#   powershell -File index.ps1                  # corpus "calames" par défaut
#   powershell -File index.ps1 -Corpus test

param(
    [string]$Corpus = "calames"
)

$root = $PSScriptRoot

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

Write-Host "Indexation du corpus '$Corpus'"
Write-Host "  Index    : $index"
Write-Host "  Data dir : $dataDir"
Write-Host ""

& "$root\es-dev.ps1"
if ($LASTEXITCODE -ne 0) { exit 1 }

Set-Location "$root\backend\indexer"
python indexer.py $dataDir --host http://localhost:9200 --index $index
