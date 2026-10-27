# Déploiement de la démo (Docker)

## Architecture

| Service | Rôle |
|---|---|
| `frontend` | nginx : sert l'application Vue et relaie `/api/*` vers FastAPI. **Seul port exposé.** |
| `api` | FastAPI. Reçoit les dépôts (`POST /upload`) et les écrit dans le dossier EAD. |
| `watcher` | Surveille le dossier EAD toutes les 5 s : indexe les fichiers nouveaux ou modifiés, retire ceux qui ont été supprimés. |
| `meilisearch` | Index de recherche (non exposé). |

Au premier démarrage, le dossier EAD est vide : le watcher y copie les 10 fichiers de
`demo/seed/`, puis les indexe (environ 10 s).

## Installation sur le serveur

Prérequis : Docker avec le plugin `compose`, et git.

Le dépôt est public : aucune authentification n'est nécessaire pour le cloner.

```sh
git clone https://github.com/yannnic/calames-html.git && cd calames-html
cp .env.example .env
# Renseigner au minimum MEILI_MASTER_KEY (openssl rand -hex 24) et UPLOAD_TOKEN
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
