# Frontend — Calames HTML

Application Vue 3 (Vite) de recherche et navigation. Voir le [README](../README.md) du projet.

```bash
npm install
npm run dev        # http://localhost:5173, API sur http://localhost:8000 (VITE_API_URL)
npm run build      # dist/ (servi par nginx en Docker, API sous /api)
```

## Organisation

| Dossier / fichier | Rôle |
|---|---|
| `src/api.js` | Appels à l'API ; corpus (`?corpus=test`, mémorisé pour l'onglet) ; réglages LLM envoyés en en-têtes |
| `src/router.js` | Routes, dont la redirection des adresses Calames (`/pub/ms/<id>`, `/pub/#details?id=`) |
| `src/views/` | Pages : accueil, recherche, recherche avancée, fonds, composant, personnes, dépôt, paramètres |
| `src/components/ChildrenTree.vue`, `ComponentTree.vue`, `ComponentSummary.vue` | Arbre des enfants et dépliage des descriptions (seuils : `src/utils/expand.js`) |
| `src/components/ExtraDescription.vue` | Producteur, organisme responsable, anciennes cotes, rubriques EAD, versions numériques |
| `src/components/RawEad.vue` | XML EAD natif d'un niveau |
| `src/components/ResultNav.vue`, `src/utils/results.js` | Navigation entre résultats et « Retour aux résultats » |
| `src/components/TestFileComment.vue`, `src/utils/origin.js` | Corpus de test : description des fichiers, valeurs propres ou héritées |
| `src/utils/labels.js` | Libellés de Calames : rubriques, rôles, langues (repris de `corresp.js` et `traductions.js` de calames.abes.fr) |
