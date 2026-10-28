<template>
  <div class="container">
    <div class="hero">
      <h1>Catalogue des archives et manuscrits</h1>
      <p class="hero-sub">
        Recherche et navigation dans les fonds d'archives des bibliothèques de l'enseignement supérieur français
      </p>
      <form class="search-bar hero-search" @submit.prevent="goSearch">
        <input v-model="q" type="text" placeholder="Rechercher par titre, sujet, lieu, personne…" autofocus />
        <button class="btn" type="submit">Rechercher</button>
      </form>
      <div class="institution-filter" v-if="byInstitution.length">
        <label for="inst-select">Institution&nbsp;</label>
        <select id="inst-select" v-model="selectedGroup">
          <option value="">Toutes les institutions</option>
          <option v-for="g in byInstitution" :key="g.repository_id || g.repository" :value="g.repository_id || g.repository">
            {{ g.repository || 'Non précisée' }} ({{ g.fonds.length }})
          </option>
        </select>
        <button v-if="selectedGroup" class="btn-clear" @click="selectedGroup = ''" title="Effacer">×</button>
      </div>
    </div>

    <section>
      <h2 style="margin-bottom:1rem">
        Fonds disponibles
        <span v-if="fondsList.length" style="font-weight:normal;font-size:.9rem;color:var(--color-muted)">
          — {{ fondsList.length }} fonds, {{ byInstitution.length }} institutions
        </span>
      </h2>
      <p v-if="loading" class="loading">Chargement…</p>
      <p v-else-if="error" class="error">{{ error }}</p>
      <div v-else>
        <details
          v-for="group in byInstitution"
          :key="group.repository_id || group.repository"
          class="institution-block"
          :open="selectedGroup === (group.repository_id || group.repository)"
          @toggle="onToggle(group.repository_id || group.repository, $event)"
        >
          <summary class="institution-header" @click.prevent="toggleGroup(group.repository_id || group.repository)">
            <span class="institution-name">{{ group.repository || 'Institution non précisée' }}</span>
            <div style="display:flex;align-items:center;gap:.8rem">
              <span class="institution-count">{{ group.fonds.length }} fonds</span>
              <button
                class="btn btn-sm btn-ghost"
                style="font-size:.75rem;padding:1px 8px"
                @click.stop="searchInstitution(group)"
              >Rechercher</button>
            </div>
          </summary>
          <ul class="result-list institution-list">
            <li v-for="fonds in group.fonds" :key="fonds.ead_id" class="result-card">
              <div>
                <span class="level-badge level-fonds">Fonds</span>
                <ChildrenDensity :count="fonds.children_count ?? 0" style="margin-right:.3rem" />
                <RouterLink :to="{ name: 'fonds', params: { eadId: fonds.ead_id } }" class="title">
                  {{ fonds.title }}
                </RouterLink>
              </div>
              <div class="meta">
                <span v-if="fonds.unitid">{{ fonds.unitid }}</span>
                <span v-if="fonds.unitid && fonds.date_display"> &nbsp;·&nbsp; </span>
                <span v-if="fonds.date_display">{{ fonds.date_display }}</span>
              </div>
              <p v-if="fonds.abstract" class="excerpt">{{ fonds.abstract }}</p>
              <TestFileComment :comment="fonds.file_comment" summary />
            </li>
          </ul>
        </details>
      </div>
    </section>
  </div>
</template>

<script>
export default { name: 'HomeView' }
</script>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { api } from '../api'
import ChildrenDensity from '../components/ChildrenDensity.vue'
import TestFileComment from '../components/TestFileComment.vue'

const router = useRouter()
const q = ref('')
const selectedGroup = ref('')   // repository_id or repository label
const fondsList = ref([])
const loading = ref(true)
const error = ref(null)
const openGroups = ref(new Set())

const byInstitution = computed(() => {
  const map = new Map()
  for (const fonds of fondsList.value) {
    // Group by repository_id when available, fall back to label
    const rid = (fonds.repository_id || '').trim()
    const key = rid || fonds.repository || ''
    if (!map.has(key)) map.set(key, { repository_id: rid, repository: fonds.repository || '', fonds: [] })
    map.get(key).fonds.push(fonds)
  }
  return Array.from(map.values())
    .sort((a, b) => a.repository.localeCompare(b.repository, 'fr', { sensitivity: 'base' }))
})

watch(selectedGroup, (val) => {
  openGroups.value = val ? new Set([val]) : new Set()
})

function toggleGroup(key) {
  if (openGroups.value.has(key)) {
    openGroups.value = new Set([...openGroups.value].filter(r => r !== key))
    if (selectedGroup.value === key) selectedGroup.value = ''
  } else {
    openGroups.value = new Set([...openGroups.value, key])
    selectedGroup.value = key
  }
}

function onToggle(key, e) {
  if (!e.target.open) {
    openGroups.value = new Set([...openGroups.value].filter(r => r !== key))
    if (selectedGroup.value === key) selectedGroup.value = ''
  }
}

function goSearch() {
  const group = byInstitution.value.find(g => (g.repository_id || g.repository) === selectedGroup.value)
  router.push({
    path: '/search',
    query: {
      q: q.value.trim() || undefined,
      repository_id: group?.repository_id || undefined,
      repository: !group?.repository_id ? (group?.repository || undefined) : undefined,
    },
  })
}

function searchInstitution(group) {
  router.push({
    path: '/search',
    query: group.repository_id
      ? { repository_id: group.repository_id }
      : { repository: group.repository },
  })
}

onMounted(async () => {
  try {
    fondsList.value = await api.listFonds()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.hero {
  text-align: center;
  padding: 2.5rem 0 2.8rem;
}
.hero-sub {
  color: var(--color-muted);
  margin: .5rem 0 1.8rem;
  font-size: .95rem;
}
.hero-search {
  max-width: 620px;
  margin: 0 auto;
}
.institution-filter {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: .5rem;
  margin-top: .9rem;
  font-size: .88rem;
  color: var(--color-muted);
}
.institution-filter select {
  padding: .3rem .6rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  font-size: .88rem;
  font-family: inherit;
  max-width: 340px;
}
.btn-clear {
  background: none;
  border: none;
  color: var(--color-muted);
  font-size: 1.1rem;
  cursor: pointer;
  line-height: 1;
  padding: 0 .2rem;
}
.btn-clear:hover { color: var(--color-text); }

.institution-block {
  margin-bottom: .5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  overflow: hidden;
}
.institution-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: .6rem 1rem;
  cursor: pointer;
  user-select: none;
  list-style: none;
  background: var(--color-bg);
  border-bottom: 1px solid transparent;
  gap: 1rem;
}
.institution-block[open] .institution-header {
  border-bottom-color: var(--color-border);
}
.institution-header::-webkit-details-marker { display: none; }
.institution-header:hover { background: rgba(26,74,122,.05); }
.institution-name { font-weight: bold; font-size: .92rem; }
.institution-count { font-size: .8rem; color: var(--color-muted); white-space: nowrap; }
.institution-list { padding: .6rem .8rem .8rem; }
</style>
