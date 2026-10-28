# Déploiement de la démo (Docker)

## Architecture

| Service | Rôle |
|---|---|
| `frontend` | nginx : sert l'application Vue et relaie `/api/*` vers FastAPI. **Seul port exposé.** |
| `api` | FastAPI. Reçoit les dépôts (`POST /upload`) et les écrit dans le dossier EAD. Réindexe le corpus de test (`data/test`, monté en lecture seule) à chaque démarrage. |
| `watcher` | Surveille le dossier EAD toutes les 5 s : indexe les fichiers nouveaux ou modifiés, retire ceux qui ont été supprimés, applique les changements de `liaisons.tsv`. |
| `harvester` | Optionnel (profil `harvest`) : moissonne l'entrepôt OAI-PMH dans le dossier EAD. |
| `elasticsearch` | Index de recherche (nœud unique, non exposé, mot de passe `ELASTIC_PASSWORD`). |

Au premier démarrage, le dossier EAD est vide : le watcher y copie les 10 fichiers de
`demo/seed/`, puis les indexe (environ 10 s).

## Installation sur le serveur

Prérequis : Docker avec le plugin `compose`, et git. Sous Linux, régler `vm.max_map_count` comme
le recommande Elastic : `sudo sysctl -w vm.max_map_count=262144` (à rendre persistant dans
`/etc/sysctl.conf`).

Mémoire : Elasticsearch réserve `ES_JAVA_OPTS` de heap (1 Go par défaut), prévoir au moins 3 Go
de RAM pour la stack. Pour tout Calames (~1,5 million de composants), passer à
`ES_JAVA_OPTS=-Xms2g -Xmx2g` et prévoir 5 Go de RAM et 5 Go de disque (EAD + index).

```sh
git clone https://github.com/yannnic/website4calamesData.git && cd website4calamesData
cp .env.example .env
# Renseigner au minimum ELASTIC_PASSWORD (openssl rand -hex 24) et UPLOAD_TOKEN
docker compose up -d --build
docker compose logs -f watcher     # suivre l'indexation
```

L'application est servie sur `http://<serveur>:${HTTP_PORT}`. Le corpus de test (fichiers ad hoc
de `data/test/`) s'ouvre avec `http://<serveur>/?corpus=test`.

Une fois la première indexation terminée, redémarrer l'API pour qu'elle construise le prompt de
recherche en langage naturel à partir des valeurs réellement indexées :
`docker compose restart api` (utile seulement si un LLM est utilisé). Le LLM se configure dans la
page **Paramètres** de chaque navigateur ; `NL_LLM_*` dans `.env` définit un LLM par défaut du
serveur (optionnel).

### HTTPS

La stack ne gère pas TLS. Placer un reverse proxy devant (Caddy, Traefik, nginx de l'hôte) et
passer `HTTP_PORT` à un port local, par ex. `HTTP_PORT=127.0.0.1:8080`.

### Adresses de Calames

Les adresses publiques de Calames (`/pub/ms/FileId-<N>`, `/pub/ms/<@id d'un composant>`,
`/pub/#details?id=<id>`) redirigent vers les pages correspondantes. Un nom de domaine qui
servait Calames peut donc pointer vers ce serveur sans casser les liens existants.

## Mise à jour d'une installation existante

```sh
git pull && docker compose up -d --build
```

Quand une nouvelle version change le mapping ou les analyseurs de l'index, le watcher le
détecte au démarrage (« Index … incompatible avec cette version : recréé »), recrée l'index vide
et **réindexe tout le dossier EAD** : la recherche est incomplète pendant ce temps (une vingtaine
de minutes pour tout Calames). Redémarrer ensuite l'API (`docker compose restart api`).

**Nommage des fichiers moissonnés.** Depuis l'ajout du numéro OAI aux noms de fichiers
(`…_oai<N>.xml`), un dossier moissonné par une version antérieure contient des noms à l'ancienne
et des notices écrasées (plusieurs notices au même `eadid`). Repartir d'un dossier vide :

```sh
docker compose --profile harvest stop harvester
docker compose stop watcher api
docker compose rm -f watcher api harvester
docker volume rm website4calamesdata_ead_data website4calamesdata_watcher_state   # ou vider EAD_DIR sur l'hôte
docker compose up -d
docker compose run --rm harvester                                  # moissonnage complet
```

(Le préfixe des volumes est le nom du dossier du projet : `docker volume ls` pour le vérifier.)

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

**Organismes responsables** : `etablissements.json` à la racine du dossier EAD (nom, adresse,
téléphone, courriel, site, par RCR). L'EAD ne les contient presque jamais : le moissonneur les
reprend, une fois par établissement, du bloc « Organisme responsable » d'une page publique de
Calames. L'API relit le fichier quand il change.

## Moissonnage OAI-PMH

Le service `harvester` moissonne un entrepôt OAI-PMH au format `oai_ead` (Calames par
défaut) et écrit les fichiers dans le dossier EAD : le watcher les indexe ensuite comme
n'importe quel dépôt. Il est désactivé par défaut. Pour le configurer, dans `.env` :

```
HARVEST_SETS=751059803,340329801   # setSpec (code RCR de l'établissement) ; vide = tout
HARVEST_LIMIT=                      # max de notices par set, pour tester
HARVEST_DELAY=2                     # pause entre deux requêtes (secondes)
HARVEST_EVERY_HOURS=24              # 0 = une seule passe
OAI_URL=                            # vide = https://calames.abes.fr/oai/oai2.aspx
```

```sh
docker compose run --rm harvester              # une passe, logs dans le terminal
docker compose --profile harvest up -d         # en continu, toutes les HARVEST_EVERY_HOURS h
```

Chaque passe télécharge aussi `liaisons.tsv` et complète `etablissements.json`.

Les passages suivants sont incrémentaux : seules les notices modifiées depuis le dernier
moissonnage **complet** sont récupérées (un passage limité par `HARVEST_LIMIT` ou interrompu par
une panne ne fait pas avancer la date). Changer d'entrepôt ou de sets relance un moissonnage
complet.

Sans `HARVEST_SETS`, tout Calames est moissonné : 4 041 notices (octobre 2026), 1,6 Go, environ
2 h 30 avec `HARVEST_DELAY=2`.

Pour ménager le serveur source, les requêtes sont strictement séquentielles :
- pause de `HARVEST_DELAY` secondes (2 par défaut) après chaque requête ;
- en cas de surcharge (HTTP 429, 5xx) ou d'erreur réseau, jusqu'à 6 nouvelles tentatives
  avec une attente qui double à chaque fois (4 s, 8 s… jusqu'à 10 min), ou la durée
  indiquée par le serveur (`Retry-After`) ;
- après 5 notices en échec d'affilée, le passage s'arrête ; le suivant reprendra depuis
  la date du dernier moissonnage complet.

Une notice que le serveur refuse ou ne sait pas produire (HTTP 4xx, erreur OAI, réponse non XML)
est **rejetée** : le passage continue, la date avance, et la notice est listée dans le fichier
d'état (`/state/harvester.json`, clé `rejected`). En octobre 2026, Calames refuse ainsi 5 notices
(123, 144, 145, 2114, 4672).

Les fichiers sont nommés d'après leur `eadid`, suivi de `_oai<N>` (numéro OAI de la notice, qui
est son FileId Calames) quand l'eadid ne contient pas déjà ce FileId : plusieurs notices
partagent parfois le même eadid, et s'écraseraient sinon. Une notice déjà présente est
remplacée, pas dupliquée.

Limite : Calames ne signale pas les notices supprimées (`deletedRecord=no`), elles restent donc
dans le dossier.

## Opérations courantes

```sh
git pull && docker compose up -d --build              # mise à jour (voir plus haut)
docker compose logs -f watcher api                     # logs
docker compose down                                     # arrêt (données conservées)
docker compose down -v                                  # arrêt + suppression des index et des dépôts
```

Réindexation complète : supprimer l'état du watcher et le redémarrer.

```sh
docker compose exec watcher rm /state/watcher.json && docker compose restart watcher
```
