export const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// Corpus de test : ouvrir le site avec ?corpus=test (mémorisé pour l'onglet,
// ?corpus= pour revenir au corpus principal).
function initCorpus() {
  try {
    const param = new URLSearchParams(window.location.search).get('corpus')
    if (param !== null) {
      if (param) sessionStorage.setItem('corpus', param)
      else sessionStorage.removeItem('corpus')
    }
    return sessionStorage.getItem('corpus') || ''
  } catch {
    return ''
  }
}
export const CORPUS = initCorpus()

export function apiUrl(path, params = {}) {
  const url = new URL(BASE + path, window.location.origin)
  Object.entries({ ...params, corpus: CORPUS }).forEach(([k, v]) => {
    if (v !== null && v !== undefined && v !== '') url.searchParams.set(k, v)
  })
  return url.toString()
}

// Réglages du LLM (page Paramètres) : gardés dans ce navigateur, envoyés à
// l'API avec les requêtes IA. Vides : configuration du serveur, s'il en a une.
const LLM_KEY = 'llmSettings'
export const LLM_DEFAULTS = { baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' }

export function loadLlmSettings() {
  try {
    return { baseUrl: '', apiKey: '', model: '', ...JSON.parse(localStorage.getItem(LLM_KEY) || '{}') }
  } catch {
    return { baseUrl: '', apiKey: '', model: '' }
  }
}

export function saveLlmSettings(settings) {
  try { localStorage.setItem(LLM_KEY, JSON.stringify(settings)) } catch { /* stockage indisponible */ }
}

function llmHeaders() {
  const { baseUrl, apiKey, model } = loadLlmSettings()
  const headers = {}
  if (baseUrl.trim()) headers['X-LLM-Base-Url'] = baseUrl.trim()
  if (apiKey.trim())  headers['X-LLM-Api-Key']  = apiKey.trim()
  if (model.trim())   headers['X-LLM-Model']    = model.trim()
  return headers
}

async function fetchOk(path, params, headers = {}) {
  const url = apiUrl(path, params)
  const res = await fetch(url, { headers })
  if (!res.ok) throw new Error(`API error ${res.status}: ${url}`)
  return res
}

async function get(path, params = {}, headers = {}) {
  return (await fetchOk(path, params, headers)).json()
}

export const api = {
  listPersons: (params = {}) => get('/persons', params),
  listFonds: () => get('/fonds'),
  getFonds: (eadId) => get(`/fonds/${encodeURIComponent(eadId)}`),
  getComponent: (nodeId) => get('/component', { node_id: nodeId }),
  getChildren:  (nodeId, details = false) =>
    get('/children', { node_id: nodeId, details: details ? 'true' : '' }),
  getSubtree:   (nodeId, max) => get('/subtree', { node_id: nodeId, max }),
  getAncestors: (nodeId) => get('/ancestors', { node_id: nodeId }),
  resolve:      (calamesId) => get('/resolve', { id: calamesId }),
  getRaw: async (nodeId, children = false) =>
    (await fetchOk('/raw', { node_id: nodeId, children: children ? 'true' : '' })).text(),
  search:     (params) => get('/search',    params),
  nlSearch:   (params) => get('/nlsearch',  params, llmHeaders()),
  summarize:  (params) => get('/summarize', params, llmHeaders()),
  checkLlm:   () => get('/llm/check', {}, llmHeaders()),
  getPerson: (params = {}) => get('/person', params),
  listFiles: () => get('/files'),
  upload: async (file, token) => {
    const body = new FormData()
    body.append('file', file)
    const res = await fetch(apiUrl('/upload'), {
      method: 'POST', body, headers: { 'X-Upload-Token': token },
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail ?? `API error ${res.status}`)
    return data
  },
}
