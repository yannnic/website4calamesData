# Arrête tous les processus du mode développement (Elasticsearch, API, Vite).
#
# Usage :
#   powershell -File stop.ps1

function Stop-Port {
    param([int]$Port, [string]$Label)
    $pid_ = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -First 1
    if ($pid_) {
        # /T : avec ses processus enfants (worker uvicorn --reload, node lancé par npm)
        taskkill /T /F /PID $pid_ *> $null
        Write-Host "  $Label (port $Port) arrêté  [pid $pid_]"
    } else {
        Write-Host "  $Label (port $Port) : rien à arrêter"
    }
}

Write-Host ""
Write-Host "Arrêt de l'environnement de développement..."
Stop-Port 8000 "API FastAPI"
Stop-Port 5173 "Frontend Vite"
Stop-Port 5174 "Frontend Vite (alt)"
docker stop calames-es 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) { Write-Host "  Elasticsearch (conteneur calames-es) arrêté" }
else { Write-Host "  Elasticsearch (conteneur calames-es) : rien à arrêter" }
Write-Host ""
