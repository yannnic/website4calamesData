<template>
  <div class="container">
    <h1 style="margin-bottom:.6rem">Index des personnes</h1>
    <p class="index-subtitle">Personnes identifiées par un identifiant IdRef / Sudoc</p>

    <!-- Barre de recherche -->
    <div class="persons-search">
      <input
        v-model="searchQ"
        type="text"
        placeholder="Rechercher un nom…"
        @input="onSearchInput"
      />
      <button v-if="searchQ" class="clear-btn" @click="clearSearch">×</button>
    </div>

    <!-- Alphabet principal -->
    <nav class="alphabet" aria-label="Navigation alphabétique">
      <button
        v-for="l in LETTERS" :key="l"
        class="alpha-btn"
        :class="{ active: activeLetter === l && !activeSubletter && !searchQ }"
        @click="selectLetter(l)"
      >{{ l }}</button>
    </nav>

    <!-- Sous-alphabet (2e niveau) -->
    <nav v-if="activeLetter && hasMore && !searchQ" class="alphabet sub-alphabet" aria-label="Affiner par sous-lettre">
      <span class="sub-label">{{ activeLetter }}… :</span>
      <button
        v-for="l in LETTERS" :key="l"
        class="alpha-btn alpha-btn--sub"
        :class="{ active: activeSubletter === l }"
        @click="selectSubletter(l)"
      >{{ l }}</button>
    </nav>

    <!-- Sous-sous-alphabet (3e niveau) -->
    <nav v-if="activeSubletter && hasMore && !searchQ" class="alphabet sub-alphabet" aria-label="Affiner encore">
      <span class="sub-label">{{ activeLetter }}{{ activeSubletter }}… :</span>
      <button
        v-for="l in LETTERS" :key="l"
        class="alpha-btn alpha-btn--sub"
        :class="{ active: activeSubsubletter === l }"
        @click="selectSubsubletter(l)"
      >{{ l }}</button>
    </nav>

    <!-- État -->
    <p v-if="loading" class="loading" style="margin-top:1rem">Chargement…</p>
    <p v-else-if="error" class="error" style="margin-top:.8rem">{{ error }}</p>

    <!-- Liste -->
    <template v-else-if="persons.length">
      <p class="persons-count">{{ persons.length }} personne{{ persons.length > 1 ? 's' : '' }}{{ hasMore ? ' (premiers résultats)' : '' }}</p>
      <ul class="persons-list">
        <li v-for="p in persons" :key="p.name">
          <RouterLink
            :to="p.idref_id
              ? { name: 'person-idref', params: { id: p.idref_id } }
              : { name: 'person', params: { name: p.name } }"
            class="person-link"
          >{{ displayName(p.name) }}</RouterLink>
          <span class="person-count">{{ p.count }}</span>
        </li>
      </ul>
    </template>
    <p v-else-if="activeLetter || searchQ" class="empty">Aucune personne trouvée.</p>
    <p v-else class="hint">Choisissez une lettre ou tapez un nom.</p>

  </div>
</template>

<script setup>
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'

const LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')

const persons        = ref([])
const hasMore        = ref(false)
const loading        = ref(false)
const error          = ref(null)
const activeLetter   = ref('')
const activeSubletter    = ref('')
const activeSubsubletter = ref('')
const searchQ        = ref('')

let searchTimer = null

// "Nom, Prénom (dates)" → "Prénom Nom (dates)"
function displayName(n) {
  const m = n.match(/^([^,]+),\s*(.+)$/)
  if (!m) return n
  const dm = m[2].match(/^(.*?)\s*(\([\d.–\-?]+\))$/)
  if (dm) return `${dm[1].trim()} ${m[1]} ${dm[2]}`
  return `${m[2].trim()} ${m[1]}`
}

function currentPrefix() {
  if (activeSubsubletter.value) return activeLetter.value + activeSubletter.value + activeSubsubletter.value
  if (activeSubletter.value)    return activeLetter.value + activeSubletter.value
  return ''
}

async function fetch_(params) {
  loading.value = true
  error.value = null
  try {
    const res = await api.listPersons(params)
    persons.value = res.persons ?? []
    hasMore.value  = res.has_more ?? false
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function selectLetter(l) {
  if (activeLetter.value === l && !activeSubletter.value && !searchQ.value) return
  activeLetter.value      = l
  activeSubletter.value   = ''
  activeSubsubletter.value = ''
  searchQ.value = ''
  fetch_({ letter: l })
}

function selectSubletter(l) {
  activeSubletter.value    = l
  activeSubsubletter.value = ''
  fetch_({ prefix: activeLetter.value + l })
}

function selectSubsubletter(l) {
  activeSubsubletter.value = l
  fetch_({ prefix: activeLetter.value + activeSubletter.value + l })
}

function clearSearch() {
  searchQ.value = ''
  if (activeLetter.value) {
    fetch_({ letter: activeLetter.value, prefix: currentPrefix() || undefined })
  } else {
    persons.value = []
    hasMore.value = false
  }
}

function onSearchInput() {
  clearTimeout(searchTimer)
  activeLetter.value      = ''
  activeSubletter.value   = ''
  activeSubsubletter.value = ''
  hasMore.value = false
  if (!searchQ.value.trim()) { persons.value = []; return }
  searchTimer = setTimeout(() => fetch_({ q: searchQ.value.trim() }), 250)
}
</script>

<style scoped>
.index-subtitle {
  font-size: .82rem;
  color: var(--color-muted);
  margin: 0 0 .9rem;
}
.persons-search {
  position: relative;
  max-width: 340px;
  margin-bottom: .9rem;
}
.persons-search input {
  width: 100%;
  padding: .38rem 2rem .38rem .65rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  font-size: .9rem;
  font-family: inherit;
}
.persons-search input:focus {
  outline: none;
  border-color: var(--color-primary);
}
.clear-btn {
  position: absolute;
  right: .4rem; top: 50%;
  transform: translateY(-50%);
  background: none; border: none;
  color: var(--color-muted);
  cursor: pointer; font-size: 1rem; line-height: 1;
}
.clear-btn:hover { color: var(--color-text); }

.alphabet {
  display: flex;
  flex-wrap: wrap;
  gap: .25rem;
  margin-bottom: .6rem;
}
.sub-alphabet {
  margin-top: -.2rem;
  margin-bottom: .7rem;
  padding: .4rem .6rem;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  align-items: center;
}
.sub-label {
  font-size: .75rem;
  font-weight: 700;
  color: var(--color-muted);
  margin-right: .3rem;
  text-transform: uppercase;
  letter-spacing: .04em;
  white-space: nowrap;
}
.alpha-btn {
  min-width: 2rem;
  padding: .2rem .3rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  font-size: .82rem;
  font-weight: 600;
  cursor: pointer;
  color: var(--color-muted);
  transition: border-color .12s, color .12s, background .12s;
}
.alpha-btn--sub { font-size: .75rem; min-width: 1.6rem; padding: .15rem .25rem; }
.alpha-btn:hover { border-color: var(--color-primary); color: var(--color-primary); }
.alpha-btn.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
}

.persons-count {
  font-size: .8rem;
  color: var(--color-muted);
  margin-bottom: .5rem;
}
.persons-list {
  list-style: none;
  padding: 0; margin: 0;
  columns: 2;
  column-gap: 2rem;
}
@media (min-width: 800px) { .persons-list { columns: 3; } }
@media (max-width: 500px)  { .persons-list { columns: 1; } }

.persons-list li {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: .5rem;
  padding: .18rem .3rem;
  border-radius: 3px;
  break-inside: avoid;
}
.persons-list li:hover { background: rgba(26,74,122,.04); }

.person-link {
  font-size: .88rem;
  color: var(--color-text);
  text-decoration: none;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: color .12s;
}
.person-link:hover { color: var(--color-primary); }

.person-count {
  flex-shrink: 0;
  font-size: .72rem;
  color: var(--color-muted);
  background: var(--color-border);
  border-radius: 10px;
  padding: 0 .4rem;
  line-height: 1.5;
  font-variant-numeric: tabular-nums;
}

.hint { color: var(--color-muted); font-size: .9rem; margin-top: 1rem; }
</style>
