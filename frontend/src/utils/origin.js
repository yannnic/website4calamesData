// Corpus de test : distinguer les valeurs propres d'un composant de celles qu'il
// hérite de ses ancêtres (index : <champ>_own, inherited_fields, date_from_children).
import { CORPUS } from '../api'

export const SHOW_ORIGIN = CORPUS === 'test'

// Valeur d'une autorité cumulative (sujets, personnes…) venue d'un ancêtre.
export function isInheritedTerm(doc, field, value) {
  const own = doc?.[`${field}_own`]
  return SHOW_ORIGIN && Array.isArray(own) && !own.includes(value)
}

// Champ à héritage simple (langue, accès, organisme, date) rempli par un ancêtre.
export function isInheritedField(doc, field) {
  return SHOW_ORIGIN && !!doc?.inherited_fields?.includes(field)
}

// Libellé de l'origine d'une date, ou '' si elle est déclarée par le composant.
export function dateOrigin(doc) {
  if (isInheritedField(doc, 'date')) return 'héritée'
  if (SHOW_ORIGIN && doc?.date_from_children) return 'calculée d\'après les enfants'
  return ''
}
