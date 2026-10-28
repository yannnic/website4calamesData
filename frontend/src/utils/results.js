// Dernière liste de résultats, pour naviguer de résultat en résultat depuis
// une notice (composant ResultNav), comme dans Calames. Mémorisée pour l'onglet.
const KEY = 'lastResults'

export function saveResults(url, hits) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify({
      url, items: hits.map(h => ({ node_id: h.node_id, ead_id: h.ead_id, depth: h.depth })),
    }))
  } catch { /* stockage indisponible */ }
}

export function loadResults() {
  try {
    return JSON.parse(sessionStorage.getItem(KEY) || 'null') ?? { items: [] }
  } catch {
    return { items: [] }
  }
}
