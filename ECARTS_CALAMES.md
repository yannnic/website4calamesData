# Écarts avec l'interface publique de Calames

État au 28 octobre 2026, d'après un parcours de [calames.abes.fr](https://calames.abes.fr/pub/)
(accueil, recherche simple et avancée, page d'établissement, fonds, composant) et ses fichiers de
libellés (`traductions.js`, `corresp.js`). Les pages construites en JavaScript (liste des
résultats, feuilletage des index) n'ont pas pu être observées : les points qui en dépendent sont
marqués *à vérifier*.

## Ce qui manque

**Écartés pour l'instant :**

- **Feuilletage des index** (sujet, personne, collectivité, lieu, titre d'œuvre, famille), avec
  « Correspondants », « Préciser » et le champ « Rôle ». Seul l'index des personnes existe.
- **Export PDF et impression** d'un inventaire et de ses composants descendants.
- **Pages d'information** : données personnelles, CGU, mentions légales, accessibilité, à propos,
  aide, assistance, crédits.

**Pas encore fait :**

- **Entrée secondaire** : le second terme d'un `<controlaccess>` qui qualifie le premier (par
  exemple une personne précisée par un lieu), ni indexé ni cherchable.
- **Services autour des notices** (connus par les libellés de Calames) : « Réserver ou commander
  le document », commentaires des usagers et leurs flux RSS par bibliothèque ou par composant,
  comptes professionnels pour la gestion des images.
- **Interface en anglais** : Calames est bilingue (français, anglais).
- **Syntaxe `mot1 =mot2`** (même nombre d'occurrences des deux mots), marginale.
- **Mise en évidence des mots cherchés** dans les résultats (*à vérifier* côté Calames).

## Ce qui est partiel

| Fonction | Ici | Calames |
|---|---|---|
| Organisme responsable | Adresse, téléphone, courriel, site pour 75 établissements (repris du bloc « Organisme responsable » des pages Calames) ; le nom seul pour les autres | Annuaire interne des établissements |
| Numérisation | Version numérique du composant qui la porte (`has_dao`) | Présence propagée aussi aux ancêtres et aux descendants |
| Liens IdRef (PPN) | Personnes seulement | Personnes, et en partie les sujets |
| Recherche simple | Une boîte, complétée par les facettes, la recherche avancée et la recherche dans un fonds | Champs séparés : mots-clés, bibliothèque(s), cote, fonds |
| Dates dans le plein texte | Date du plus proche ancêtre daté, en texte et en période filtrable | Dates de tous les ancêtres, en texte |

## Ce qui diffère dans les données

- **Fraîcheur** : moissonnage complet du 28 octobre 2026 ; Calames évolue chaque jour.
- **5 notices absentes**, que le serveur Calames refuse de produire en OAI-PMH : 123, 144, 145,
  2114, 4672.
- **Notices supprimées** : Calames ne les signale pas en OAI (`deletedRecord=no`) ; une notice
  retirée de Calames reste ici.
- **3 fichiers à `@id` en double** : un composant perdu par doublon.
- **Ordre sous un fichier de tête** qui a à la fois ses propres composants, des fichiers inclus et
  des successeurs : composants propres, puis fichiers inclus, puis successeurs (*à vérifier* chez
  Calames).

## Ce qui diffère dans le comportement

- **Regroupement des résultats** : un parent remplace ses descendants trouvés quand au moins 75 %
  de ses enfants correspondent (*à vérifier* : Calames semble présenter une liste à plat).
  Désactivé quand un filtre de niveau est actif.
- **Plein texte** : pondéré (titre et cote d'abord, valeurs propres avant valeurs héritées, titres
  des ancêtres en complément) ; Calames concatène tout dans une seule colonne. Détail dans
  [INDEXING.md](INDEXING.md#plein-texte--comparaison-avec-calames).
- **Adresses** : différentes, mais celles de Calames (`/pub/ms/<FileId-N ou @id>` et
  `/pub/#details?id=`) redirigent vers les pages correspondantes.

## Repris de Calames

- Liaisons entre fichiers (`liaisons.tsv`) : inclusion, et succession formant un seul fonds.
- Libellés des rubriques de description, des rôles et des langues.
- Organisme responsable, anciennes cotes, versions numériques, titres d'œuvres, fonctions,
  provenance (propriétaire précédent).
- Tri des résultats (pertinence, titre, date), navigation résultat précédent / suivant / retour.
- Syntaxe de recherche : `OR` ou `|`, `-exclu`, `+requis`, `^début`.
- Recherche dans un fonds, facettes langues et propriétaire précédent, filtre « documents
  numérisés associés », pictogrammes des types de document.

## En plus de Calames

- Recherche en langage naturel et résumé des résultats par LLM.
- Dépliage des descriptions des enfants dans l'arbre (un enfant, tous les enfants jusqu'à 50, tout
  le sous-arbre jusqu'à 200 composants).
- XML EAD natif à chaque niveau ; curseur de navigation entre frères.
- Facettes supplémentaires : siècle, niveau, technique.
- Corpus de test, avec l'origine des valeurs (propre ou héritée).
- Dépôt de fichiers EAD par le web.

## Pistes prioritaires

1. **Entrée secondaire** : indexation et recherche.
2. **Mise en évidence des mots cherchés** dans les résultats.
3. **Numérisation propagée** aux ancêtres, comme Calames.
4. **Feuilletage des index**, puis export PDF et pages d'information.
