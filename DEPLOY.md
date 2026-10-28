# Déploiement de la démo (Docker)

## Architecture

| Service | Rôle |
|---|---|
| `frontend` | nginx : sert l'application Vue et relaie `/api/*` vers FastAPI. **Seul port exposé.** |
| `api` | FastAPI. Reçoit les dépôts (`POST /upload`) et les écrit dans le dossier EAD. |
| `watcher` | Surveille le dossier EAD toutes les 5 s : indexe les fichiers nouveaux ou modifiés, retire ceux qui ont été supprimés. |
| `elasticsearch` | Index de recherche (nœud unique, non exposé, mot de passe `ELASTIC_PASSWORD`). |

Au premier démarrage, le dossier EAD est vide : le watcher y copie les 10 fichiers de
`demo/seed/`, puis les indexe (environ 10 s).

## Installation sur le serveur

Prérequis : Docker avec le plugin `compose`, et git. Elasticsearch réserve 1 Go de heap
(`ES_JAVA_OPTS`) : prévoir au moins 3 Go de RAM pour la stack. Sous Linux, régler
`vm.max_map_count` comme le recommande Elastic :
`sudo sysctl -w vm.max_map_count=262144` (à rendre persistant dans `/etc/sysctl.conf`).

Le dépôt est public : aucune authentification n'est nécessaire pour le cloner.

```sh
git clone https://github.com/yannnic/calames-html.git && cd calames-html
cp .env.example .env
# Renseigner au minimum ELASTIC_PASSWORD (openssl rand -hex 24) et UPLOAD_TOKEN
docker compose up -d --build
docker compose logs -f watcher     # suivre l'indexation
```

L'application est servie sur `http://<serveur>:${HTTP_PORT}`.

Une fois la première indexation terminée, redémarrer l'API pour qu'elle construise le prompt
de recherche en langage naturel à partir des valeurs réellement indexées :
`docker compose restart api` (utile seulement si `NL_LLM_*` est renseigné).

### HTTPS

La stack ne gère pas TLS. Placer un reverse proxy devant (Caddy, Traefik, nginx de l'hôte)
et passer `HTTP_PORT` à un port local, par ex. `HTTP_PORT=127.0.0.1:8080`.

## Ajouter des fichiers EAD

**Par le web** : page **Déposer** (`/depot`), avec le jeton `UPLOAD_TOKEN`. Le fichier doit
être un XML bien formé dont la racine est `<ead>` ; un fichier du même nom est remplacé.
Le tableau affiche le statut d'indexation (en attente, indexé, erreur de parsing).

**Par le système de fichiers** : définir `EAD_DIR=/srv/calames/ead` dans `.env` pour utiliser
un dossier de l'hôte à la place du volume Docker, puis y copier les fichiers (scp, SFTP…).
Supprimer un fichier le retire de l'index. Seuls les `*.xml` à la racine du dossier sont pris
en compte.

**Liaisons entre fichiers** : un `liaisons.tsv` à la racine du dossier EAD (format Calames,
voir [INDEXING.md](INDEXING.md#liaisons-entre-fichiers-liaisonstsv)) réunit les fichiers liés
en une seule hiérarchie. Le moissonneur le télécharge à chaque passe ; le watcher applique ses
modifications (réindexation des seuls fichiers qui changent de parent).

**Organismes responsables** : `etablissements.json` à la racine du dossier EAD (adresse,
téléphone, courriel, site par RCR), complété par le moissonneur à chaque passe ; l'API le relit
quand il change.

## Moissonnage OAI-PMH

Le service `harvester` moissonne un entrepôt OAI-PMH au format `oai_ead` (Calames par
défaut) et écrit les fichiers dans le dossier EAD : le watcher les indexe ensuite comme
n'importe quel dépôt. Il est désactivé par défaut. Pour le configurer, dans `.env` :

```
HARVEST_SETS=751059803,340329801   # setSpec (code RCR de l'établissement) ; vide = tout
HARVEST_LIMIT=                      # max de notices par set, pour tester
HARVEST_EVERY_HOURS=24              # 0 = une seule passe
OAI_URL=                            # vide = https://calames.abes.fr/oai/oai2.aspx
```

```sh
docker compose run --rm harvester              # une passe, logs dans le terminal
docker compose --profile harvest up -d         # en continu, toutes les HARVEST_EVERY_HOURS h
```

Les passages suivants sont incrémentaux : seules les notices modifiées depuis le dernier
moissonnage **complet** sont récupérées (un passage limité par `HARVEST_LIMIT` ou en erreur
ne fait pas avancer la date). Changer d'entrepôt ou de sets relance un moissonnage complet.

Sans `HARVEST_SETS`, tout Calames est moissonné : environ 3 700 instruments de recherche,
1,2 Go, au moins 2 à 3 heures.

Pour ménager le serveur source, les requêtes sont strictement séquentielles :
- pause de `HARVEST_DELAY` secondes (2 par défaut) après chaque requête ;
- en cas de surcharge (HTTP 429, 5xx) ou d'erreur réseau, jusqu'à 6 nouvelles tentatives
  avec une attente qui double à chaque fois (4 s, 8 s… jusqu'à 10 min), ou la durée
  indiquée par le serveur (`Retry-After`) ;
- après 5 notices en échec d'affilée, le passage s'arrête ; le suivant reprendra depuis
  la date du dernier moissonnage complet.

Limites : Calames ne signale pas les notices supprimées (`deletedRecord=no`), elles restent
donc dans le dossier. Les fichiers sont nommés d'après leur `eadid` (comme ceux de
`demo/seed/`) : un fonds déjà présent est remplacé, pas dupliqué.

## Opérations courantes

```sh
git pull && docker compose up -d --build              # mise à jour
docker compose logs -f watcher api                     # logs
docker compose down                                     # arrêt (données conservées)
docker compose down -v                                  # arrêt + suppression des index et des dépôts
```

Réindexation complète : supprimer l'état du watcher et le redémarrer.

```sh
docker compose exec watcher rm /state/watcher.json && docker compose restart watcher
```
