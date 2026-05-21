# Arrête tous les processus du mode développement (MeiliSearch, API, Vite).
#
# Usage :
#   powershell -File stop.ps1

function Stop-Port {
    param([int]$Port, [string]$Label)
    $pid_ = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -First 1
    if ($pid_) {
        Stop-Process -Id $pid_ -Force -ErrorAction SilentlyContinue
        Write-Host "  $Label (port $Port) arrêté  [pid $pid_]"
    } else {
        Write-Host "  $Label (port $Port) : rien à arrêter"
    }
}

Write-Host ""
Write-Host "Arrêt de l'environnement de développement..."
Stop-Port 7700 "MeiliSearch"
Stop-Port 8000 "API FastAPI"
Stop-Port 5173 "Frontend Vite"
Stop-Port 5174 "Frontend Vite (alt)"
Write-Host ""
