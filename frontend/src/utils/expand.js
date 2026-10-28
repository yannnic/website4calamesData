// Dépliage des descriptions dans l'arbre EAD : ce qui reste lisible et léger.
//
// - La description d'un composant se déplie toujours, une à la fois (bouton ⓘ).
// - Celles de tous les enfants directs d'un niveau, d'un coup : jusqu'à
//   EXPAND_CHILDREN_MAX enfants (une requête). Au-delà (certains niveaux ont des
//   milliers d'enfants), la page deviendrait illisible : une à une seulement.
// - Tout le sous-arbre (structure + descriptions) : jusqu'à EXPAND_SUBTREE_MAX
//   composants (une requête /subtree). Au-delà, on ouvre niveau par niveau.

export const EXPAND_CHILDREN_MAX = 50
export const EXPAND_SUBTREE_MAX  = 200
