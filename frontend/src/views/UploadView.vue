<template>
  <div class="container">
    <h1 style="margin-bottom:.6rem">Déposer un fichier EAD</h1>
    <p class="upload-subtitle">
      Les fichiers déposés sont indexés automatiquement en quelques secondes,
      puis consultables dans la recherche et la liste des fonds.
    </p>

    <p v-if="enabled === false" class="empty">Le dépôt de fichiers est désactivé sur ce serveur.</p>

    <form v-else class="upload-form" @submit.prevent="send">
      <label>
        Jeton de dépôt
        <input v-model="token" type="password" autocomplete="current-password" required />
      </label>
      <label>
        Fichier(s) EAD (.xml)
        <input ref="fileInput" type="file" accept=".xml,text/xml,application/xml" multiple required />
      </label>
      <button type="submit" :disabled="sending">{{ sending ? 'Envoi…' : 'Déposer' }}</button>
    </form>

    <ul v-if="messages.length" class="upload-messages">
      <li v-for="m in messages" :key="m.name" :class="m.ok ? 'ok' : 'error'">
        <strong>{{ m.name }}</strong> — {{ m.text }}
      </li>
    </ul>

    <h2 class="files-title">Fichiers du corpus</h2>
    <p v-if="error" class="error">{{ error }}</p>
    <table v-else-if="files.length" class="files-table">
      <thead>
        <tr><th>Fichier</th><th>Taille</th><th>Statut</th><th>Composants</th></tr>
      </thead>
      <tbody>
        <tr v-for="f in files" :key="f.name">
          <td>{{ f.name }}</td>
          <td>{{ formatSize(f.size) }}</td>
          <td>
            <span class="status" :class="'status--' + f.status">{{ STATUS_LABELS[f.status] ?? f.status }}</span>
            <div v-if="f.error" class="file-error">{{ f.error }}</div>
          </td>
          <td>{{ f.docs ?? '—' }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="loading">Chargement…</p>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { api } from '../api'

const STATUS_LABELS = {
  pending:  'En attente',
  indexing: 'Indexation…',
  indexed:  'Indexé',
  error:    'Erreur',
}

const TOKEN_KEY = 'uploadToken'
function readToken() {
  try { return localStorage.getItem(TOKEN_KEY) ?? '' } catch { return '' }
}

const token     = ref(readToken())
const files     = ref([])
const enabled   = ref(null)
const error     = ref(null)
const sending   = ref(false)
const messages  = ref([])
const fileInput = ref(null)

watch(token, (v) => { try { localStorage.setItem(TOKEN_KEY, v) } catch { /* stockage indisponible */ } })

function formatSize(n) {
  if (n < 1024) return `${n} o`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} Ko`
  return `${(n / 1024 / 1024).toFixed(1)} Mo`
}

async function refresh() {
  try {
    const res = await api.listFiles()
    files.value = res.files
    enabled.value = res.upload_enabled
    error.value = null
  } catch (e) {
    error.value = e.message
  }
}

async function send() {
  sending.value = true
  messages.value = []
  for (const file of fileInput.value.files) {
    try {
      const res = await api.upload(file, token.value)
      messages.value.push({ name: res.name, ok: true, text: 'déposé, indexation en cours.' })
    } catch (e) {
      messages.value.push({ name: file.name, ok: false, text: e.message })
    }
  }
  fileInput.value.value = ''
  sending.value = false
  refresh()
}

let timer = null
onMounted(() => {
  refresh()
  timer = setInterval(refresh, 3000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.upload-subtitle { color: var(--color-muted); margin-bottom: 1.2rem; }

.upload-form {
  display: flex; flex-wrap: wrap; gap: 1rem; align-items: flex-end;
  background: var(--color-surface); border: 1px solid var(--color-border);
  border-radius: var(--radius); padding: 1rem; box-shadow: var(--shadow);
}
.upload-form label { display: flex; flex-direction: column; gap: .3rem; font-size: .9rem; color: var(--color-muted); }
.upload-form input[type=password] { padding: .4rem .5rem; border: 1px solid var(--color-border); border-radius: var(--radius); }
.upload-form button {
  padding: .5rem 1.2rem; border: none; border-radius: var(--radius);
  background: var(--color-primary); color: #fff; cursor: pointer;
}
.upload-form button:hover:not(:disabled) { background: var(--color-primary-hover); }
.upload-form button:disabled { opacity: .6; cursor: default; }

.upload-messages { list-style: none; padding: 0; margin: 1rem 0 0; }
.upload-messages li { padding: .3rem 0; }
.upload-messages .ok { color: #2e7d32; }
.upload-messages .error { padding: .3rem 0; }

.files-title { margin: 2rem 0 .8rem; font-size: 1.2rem; }
.files-table { width: 100%; border-collapse: collapse; background: var(--color-surface); font-size: .9rem; }
.files-table th, .files-table td { text-align: left; padding: .45rem .6rem; border-bottom: 1px solid var(--color-border); vertical-align: top; }
.files-table td:first-child { word-break: break-all; }

.status { font-size: .8rem; padding: .1rem .5rem; border-radius: 999px; background: #eee; white-space: nowrap; }
.status--indexed  { background: #e3f1e4; color: #2e7d32; }
.status--indexing,
.status--pending  { background: #fdf1de; color: #8a5a14; }
.status--error    { background: #fbe5e2; color: #c0392b; }
.file-error { color: #c0392b; font-size: .8rem; margin-top: .3rem; }
</style>
