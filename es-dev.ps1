# Démarre l'Elasticsearch de développement (conteneur Docker "calames-es", port 9200)
# et attend qu'il réponde. Idempotent : réutilise le conteneur s'il existe déjà.
#
# Usage :
#   powershell -File es-dev.ps1

$name  = "calames-es"
$image = "docker.elastic.co/elasticsearch/elasticsearch:8.19.3"

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker ne répond pas : lancer Docker Desktop."
    exit 1
}

$state = docker inspect -f "{{.State.Running}}" $name 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Création du conteneur $name..."
    docker run -d --name $name -p 9200:9200 `
        -e discovery.type=single-node `
        -e xpack.security.enabled=false `
        -e "ES_JAVA_OPTS=-Xms1g -Xmx1g" `
        -v calames_es_dev:/usr/share/elasticsearch/data `
        $image | Out-Null
} elseif ($state -ne "true") {
    docker start $name | Out-Null
}

Write-Host -NoNewline "Attente d'Elasticsearch"
for ($i = 0; $i -lt 60; $i++) {
    try {
        Invoke-RestMethod "http://localhost:9200/_cluster/health?wait_for_status=yellow&timeout=1s" -TimeoutSec 3 | Out-Null
        Write-Host " ok."
        exit 0
    } catch {
        Write-Host -NoNewline "."
        Start-Sleep -Seconds 2
    }
}
Write-Host ""
Write-Error "Elasticsearch ne répond pas sur http://localhost:9200 (docker logs $name)."
exit 1
