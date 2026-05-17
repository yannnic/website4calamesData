<template>
  <div class="container">
    <p v-if="loading" class="loading" style="padding-top:2rem">Chargement…</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <template v-else>

      <div class="person-header">
        <h1>{{ displayName }}</h1>
        <div class="person-meta">
          <span class="person-total">{{ total }} composant{{ total !== 1 ? 's' : '' }} archivistiques</span>
          <a
            v-if="idrefId"
            :href="`https://www.idref.fr/${idrefId}/id`"
            target="_blank" rel="noopener"
            class="idref-link"
          >IdRef {{ idrefId }} ↗</a>
        </div>
      </div>

      <!-- Filtre par rôle -->
      <div v-if="roles.length" class="role-filters">
        <span class="role-label">Rôles :</span>
        <button
          v-for="r in roles" :key="r.role"
          class="role-chip"
          :class="{ active: selectedRole === r.role }"
          @click="toggleRole(r.role)"
        >
          {{ r.role || 'sans rôle' }}
          <span class="role-count">{{ r.count }}</span>
        </button>
      </div>

      <!-- Résultats -->
      <ul class="result-list" style="margin-top:1rem">
        <li v-for="hit in hits" :key="hit.node_id" class="result-card">
          <nav v-if="hit.ancestor_titles?.length" class="result-breadcrumb">
            <template v-for="(title, i) in hit.ancestor_titles" :key="i">
              <RouterLink :to="cPath(hit.ancestor_ids[i])">{{ title }}</RouterLink>
              <span class="sep" aria-hidden="true">›</span>
            </template>
          </nav>
          <div>
            <span class="level-badge" :class="`level-${hit.level}`">{{ levelLabel(hit.level) }}</span>
            <ChildrenDensity :count="hit.children_count ?? 0" style="margin-right:.3rem" />
            <RouterLink :to="componentPath(hit)" class="title">{{ hit.title }}</RouterLink>
          </div>
          <div class="meta">
            <span v-if="hit.unitid">{{ hit.unitid }}</span>
            <span v-if="hit.unitid && (hit.date_display || hit.repository)"> &nbsp;·&nbsp; </span>
            <span v-if="hit.date_display">{{ hit.date_display }}</span>
            <span v-if="hit.date_display && hit.repository"> &nbsp;·&nbsp; </span>
            <span v-if="hit.repository">{{ hit.repository }}</span>
          </div>
          <p v-if="hit.abstract || hit.scope_content" class="excerpt">
            {{ hit.abstract || hit.scope_content }}
          </p>
        </li>
      </ul>

      <div v-if="total > limit" class="pagination">
        <button class="btn btn-sm" :disabled="offset === 0" @click="prevPage">← Précédent</button>
        <span>Page {{ page }} / {{ totalPages }}</span>
        <button class="btn btn-sm" :disabled="offset + limit >= total" @click="nextPage">Suivant →</button>
      </div>

    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { levelLabel } from '../utils/levels'
import { useRoute, RouterLink } from 'vue-router'
import ChildrenDensity from '../components/ChildrenDensity.vue'
import { componentPath as cPath } from '../router'
import { api } from '../api'

const route = useRoute()

const name         = ref('')
const idrefId      = ref(null)
const roles        = ref([])
const hits         = ref([])
const total        = ref(0)
const loading      = ref(true)
const error        = ref(null)
const selectedRole = ref(null)
const offset       = ref(0)
const limit        = 20

const isIdrefRoute = computed(() => route.name === 'person-idref')

const page       = computed(() => Math.floor(offset.value / limit) + 1)
const totalPages = computed(() => Math.ceil(total.value / limit))

// "Nom, Prénom (dates)" → "Prénom Nom (dates)" pour affichage
const displayName = computed(() => {
  const n = name.value
  const m = n.match(/^([^,]+),\s*(.+)$/)
  if (!m) return n
  // Séparer les dates éventuelles du prénom
  const datesMatch = m[2].match(/^(.*?)\s*(\([\d.–\-?]+\))$/)
  if (datesMatch) return `${datesMatch[1].trim()} ${m[1]} ${datesMatch[2]}`
  return `${m[2].trim()} ${m[1]}`
})

function componentPath(hit) {
  if (hit.depth === 0) return { name: 'fonds', params: { eadId: hit.ead_id } }
  return cPath(hit.node_id)
}

function toggleRole(role) {
  selectedRole.value = selectedRole.value === role ? null : role
  offset.value = 0
  load()
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const params = {
      role: selectedRole.value || undefined,
      limit,
      offset: offset.value,
    }
    if (isIdrefRoute.value) {
      params.idref_id = route.params.id
    } else {
      params.name = name.value
    }
    const res = await api.getPerson(params)
    if (res.name)    name.value    = res.name
    if (res.idref_id) idrefId.value = res.idref_id
    roles.value   = res.roles
    hits.value    = res.hits
    total.value   = res.total
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function prevPage() { offset.value -= limit; load() }
function nextPage() { offset.value += limit; load() }

onMounted(() => {
  if (!isIdrefRoute.value) name.value = decodeURIComponent(route.params.name)
  load()
})

watch(() => route.params, (params) => {
  if (params.id || params.name) {
    if (!isIdrefRoute.value) name.value = decodeURIComponent(params.name)
    selectedRole.value = null
    offset.value = 0
    load()
  }
})
</script>

<style scoped>
.person-header {
  padding: 1.5rem 0 .8rem;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 1rem;
}
.person-header h1 { margin: 0 0 .3rem; }
.person-meta {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin: 0;
}
.person-total { font-size: .88rem; color: var(--color-muted); }
.idref-link {
  font-size: .8rem;
  color: var(--color-primary);
  text-decoration: none;
  border: 1px solid var(--color-primary);
  border-radius: 99px;
  padding: .1rem .6rem;
  transition: background .15s, color .15s;
}
.idref-link:hover { background: var(--color-primary); color: #fff; }

.role-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: .4rem;
  margin-bottom: .8rem;
}
.role-label {
  font-size: .78rem;
  font-weight: 600;
  color: var(--color-muted);
  text-transform: uppercase;
  letter-spacing: .04em;
  margin-right: .2rem;
}
.role-chip {
  display: inline-flex;
  align-items: center;
  gap: .35rem;
  padding: .2rem .7rem;
  border: 1px solid var(--color-border);
  border-radius: 99px;
  background: var(--color-surface);
  font-size: .82rem;
  cursor: pointer;
  transition: border-color .15s, color .15s, background .15s;
  font-family: inherit;
}
.role-chip:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}
.role-chip.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
}
.role-count {
  font-size: .72rem;
  opacity: .7;
  font-variant-numeric: tabular-nums;
}
.role-chip.active .role-count { opacity: .85; }

.result-breadcrumb {
  display: block;
  font-size: .73rem;
  color: var(--color-muted);
  margin-bottom: .3rem;
  line-height: 1.6;
}
.result-breadcrumb a { color: inherit; text-decoration: none; border-bottom: 1px dotted transparent; }
.result-breadcrumb a:hover { color: var(--color-primary); border-bottom-color: var(--color-primary); }
.result-breadcrumb .sep { margin: 0 .3rem; color: var(--color-border); }
</style>
