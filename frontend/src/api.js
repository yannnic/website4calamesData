export const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

async function get(path, params = {}) {
  const url = new URL(BASE + path, window.location.origin)
  Object.entries(params).forEach(([k, v]) => {
    if (v !== null && v !== undefined && v !== '') url.searchParams.set(k, v)
  })
  const res = await fetch(url)
  if (!res.ok) throw new Error(`API error ${res.status}: ${url}`)
  return res.json()
}

export const api = {
  listPersons: (params = {}) => get('/persons', params),
  listFonds: () => get('/fonds'),
  getFonds: (eadId) => get(`/fonds/${encodeURIComponent(eadId)}`),
  getComponent: (nodeId) => get('/component', { node_id: nodeId }),
  getChildren:  (nodeId) => get('/children',  { node_id: nodeId }),
  getAncestors: (nodeId) => get('/ancestors', { node_id: nodeId }),
  search:     (params) => get('/search',    params),
  nlSearch:   (params) => get('/nlsearch',  params),
  summarize:  (params) => get('/summarize', params),
  getPerson: (params = {}) => get('/person', params),
  listFiles: () => get('/files'),
  upload: async (file, token) => {
    const body = new FormData()
    body.append('file', file)
    const res = await fetch(new URL(BASE + '/upload', window.location.origin), {
      method: 'POST', body, headers: { 'X-Upload-Token': token },
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail ?? `API error ${res.status}`)
    return data
  },
}
