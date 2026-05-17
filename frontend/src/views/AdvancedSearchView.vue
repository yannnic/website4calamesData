<template>
  <div class="container">
    <h1 style="margin-bottom:1.4rem">Recherche avancée</h1>

    <form class="adv-form" @submit.prevent="doSearch">

      <!-- Ligne 1 : mots-clés générale pleine largeur -->
      <div class="adv-field adv-field--full">
        <label for="adv-q">Mots-clés (tous champs)</label>
        <input id="adv-q" v-model="q" type="text" placeholder="Titre, description, cotes, noms…" autofocus />
      </div>

      <div class="adv-grid">

        <div class="adv-field">
          <label for="adv-subject">Sujet</label>
          <input id="adv-subject" v-model="subject" type="text" placeholder="ex. Droit canon" />
        </div>

        <div class="adv-field">
          <label for="adv-pers">Personne</label>
          <input id="adv-pers" v-model="persName" type="text" placeholder="ex. Voltaire" />
        </div>

        <div class="adv-field">
          <label for="adv-corp">Collectivité</label>
          <input id="adv-corp" v-model="corpName" type="text" placeholder="ex. Académie française" />
        </div>

        <div class="adv-field">
          <label for="adv-geo">Lieu</label>
          <input id="adv-geo" v-model="geoName" type="text" placeholder="ex. Paris" />
        </div>

        <div class="adv-field">
          <label for="adv-genre">Genre / forme</label>
          <input id="adv-genre" v-model="genreForm" type="text" placeholder="ex. Manuscrit" />
        </div>

        <div class="adv-field">
          <label for="adv-creator">Créateur / auteur</label>
          <input id="adv-creator" v-model="creator" type="text" placeholder="ex. Colbert" />
        </div>

        <div class="adv-field">
          <label for="adv-repo">Institution</label>
          <select id="adv-repo" v-model="repository">
            <option value="">— Toutes —</option>
            <option
              v-for="inst in institutions" :key="inst.id"
              :value="inst.name"
            >{{ inst.name }}</option>
          </select>
        </div>

        <div class="adv-field">
          <label for="adv-level">Niveau de description</label>
          <select id="adv-level" v-model="level">
            <option value="">— Tous —</option>
            <option value="fonds">Fonds</option>
            <option value="recordgrp">Ensemble de fonds</option>
            <option value="series">Série</option>
            <option value="subseries">Sous-série</option>
            <option value="file">Dossier</option>
            <option value="item">Pièce</option>
          </select>
        </div>

        <div class="adv-field">
          <label>Dates</label>
          <div class="date-range">
            <input v-model.number="dateFrom" type="number" placeholder="de" min="0" max="2100" />
            <span>–</span>
            <input v-model.number="dateTo" type="number" placeholder="à" min="0" max="2100" />
          </div>
        </div>

        <div class="adv-field">
          <label for="adv-lang">Langue</label>
          <select id="adv-lang" v-model="lang">
            <option value="">— Toutes —</option>
            <option value="fre">Français</option>
            <option value="lat">Latin</option>
            <option value="eng">Anglais</option>
            <option value="ger">Allemand</option>
            <option value="spa">Espagnol</option>
            <option value="ita">Italien</option>
            <option value="ara">Arabe</option>
            <option value="heb">Hébreu</option>
            <option value="gre">Grec</option>
          </select>
        </div>

        <div class="adv-field">
          <label for="adv-century">Période (siècle)</label>
          <select id="adv-century" v-model="century">
            <option value="">— Toutes —</option>
            <option v-for="c in CENTURIES" :key="c" :value="c">{{ c }}</option>
          </select>
        </div>

      </div><!-- fin adv-grid -->

      <div class="adv-actions">
        <button class="btn" type="submit" :disabled="loading">Rechercher</button>
        <button class="btn btn-ghost" type="button" @click="reset">Réinitialiser</button>
        <span v-if="results" style="font-size:.85rem;color:var(--color-muted)">
          {{ results.total }} résultat{{ results.total !== 1 ? 's' : '' }}
        </span>
      </div>

    </form>

    <!-- État -->
    <p v-if="loading" class="loading" style="margin-top:1.5rem">Recherche en cours…</p>
    <p v-else-if="error" class="error" style="margin-top:1rem">{{ error }}</p>

    <!-- Résultats -->
    <div v-else-if="results">
      <ul class="result-list" style="margin-top:1.2rem">
        <li v-for="hit in results.hits" :key="hit.node_id" class="result-card">
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
          <div v-if="hit.subjects?.length || hit.pers_names?.length || hit.geo_names?.length" class="tag-list">
            <span v-for="s in (hit.subjects ?? []).slice(0, 4)"   :key="'s'+s" class="tag" :title="s">{{ s }}</span>
            <RouterLink v-for="s in (hit.pers_names ?? []).slice(0, 2)" :key="'p'+s" :to="{ name: 'person', params: { name: s } }" class="tag tag--person" :title="s">{{ s }}</RouterLink>
            <span v-for="s in (hit.geo_names ?? []).slice(0, 2)"  :key="'g'+s" class="tag tag--geo" :title="s">{{ s }}</span>
          </div>
        </li>
      </ul>

      <div class="pagination">
        <button class="btn btn-sm" :disabled="offset === 0" @click="prevPage">← Précédent</button>
        <span>Page {{ page }} / {{ totalPages }}</span>
        <button class="btn btn-sm" :disabled="offset + limit >= results.total" @click="nextPage">Suivant →</button>
      </div>
    </div>

    <p v-else-if="searched" class="empty">Aucun résultat.</p>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { levelLabel } from '../utils/levels'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import ChildrenDensity from '../components/ChildrenDensity.vue'
import { componentPath as cPath } from '../router'
import { api } from '../api'

const route  = useRoute()
const router = useRouter()

const CENTURIES = [
  'Ier s.','IIe s.','IIIe s.','IVe s.','Ve s.','VIe s.','VIIe s.','VIIIe s.',
  'IXe s.','Xe s.','XIe s.','XIIe s.','XIIIe s.','XIVe s.','XVe s.','XVIe s.',
  'XVIIe s.','XVIIIe s.','XIXe s.','XXe s.','XXIe s.',
]

const q         = ref('')
const subject   = ref('')
const persName  = ref('')
const corpName  = ref('')
const geoName   = ref('')
const genreForm = ref('')
const creator   = ref('')
const repository = ref('')
const level     = ref('')
const century   = ref('')
const dateFrom  = ref(null)
const dateTo    = ref(null)
const lang      = ref('')

const limit     = 20
const offset    = ref(0)
const results   = ref(null)
const loading   = ref(false)
const error     = ref(null)
const searched  = ref(false)
const institutions = ref([])

const page       = computed(() => Math.floor(offset.value / limit) + 1)
const totalPages = computed(() => results.value ? Math.ceil(results.value.total / limit) : 1)

function componentPath(hit) {
  if (hit.depth === 0) return { name: 'fonds', params: { eadId: hit.ead_id } }
  return cPath(hit.node_id)
}

function reset() {
  q.value = ''; subject.value = ''; persName.value = ''; corpName.value = ''
  geoName.value = ''; genreForm.value = ''; creator.value = ''
  repository.value = ''; level.value = ''; century.value = ''
  dateFrom.value = null; dateTo.value = null; lang.value = ''
  offset.value = 0; results.value = null; searched.value = false
}

async function doSearch() {
  loading.value = true
  error.value = null
  searched.value = true
  try {
    results.value = await api.search({
      q:          q.value         || undefined,
      subject:    subject.value   || undefined,
      pers_name:  persName.value  || undefined,
      corp_name:  corpName.value  || undefined,
      geo_name:   geoName.value   || undefined,
      genre_form: genreForm.value || undefined,
      creator:    creator.value   || undefined,
      repository: repository.value || undefined,
      level:      level.value     || undefined,
      century:    century.value   || undefined,
      date_from:  dateFrom.value  || undefined,
      date_to:    dateTo.value    || undefined,
      lang:       lang.value      || undefined,
      limit,
      offset: offset.value,
    })
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function prevPage() { offset.value -= limit; doSearch() }
function nextPage() { offset.value += limit; doSearch() }

onMounted(async () => {
  // Charger la liste des institutions pour le select
  try {
    const fonds = await api.listFonds()
    const seen = new Map()
    for (const f of fonds) {
      if (f.repository && !seen.has(f.repository)) {
        seen.set(f.repository, f.repository_id || '')
      }
    }
    institutions.value = Array.from(seen.entries())
      .map(([name, id]) => ({ name, id }))
      .sort((a, b) => {
        const ia = parseInt(a.id) || Infinity
        const ib = parseInt(b.id) || Infinity
        return ia - ib || a.name.localeCompare(b.name)
      })
  } catch { /* silencieux */ }

  // Pré-remplir depuis les query params si on arrive depuis la recherche simple
  const q_ = route.query
  if (q_.q)          q.value          = q_.q
  if (q_.subject)    subject.value    = q_.subject
  if (q_.pers_name)  persName.value   = q_.pers_name
  if (q_.corp_name)  corpName.value   = q_.corp_name
  if (q_.geo_name)   geoName.value    = q_.geo_name
  if (q_.genre_form) genreForm.value  = q_.genre_form
  if (q_.creator)    creator.value    = q_.creator
  if (q_.repository) repository.value = q_.repository
  if (q_.level)      level.value      = q_.level
  if (q_.century)    century.value    = q_.century
  if (q_.lang)       lang.value       = q_.lang
  if (q_.date_from)  dateFrom.value   = parseInt(q_.date_from)
  if (q_.date_to)    dateTo.value     = parseInt(q_.date_to)
  if (Object.keys(q_).length) doSearch()
})
</script>

<style scoped>
.adv-form {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 1.4rem 1.6rem 1rem;
  margin-bottom: .5rem;
}

.adv-field--full {
  margin-bottom: 1rem;
}

.adv-grid {
  display: flex;
  flex-direction: column;
  gap: .7rem;
  margin-bottom: 1rem;
}

.adv-field {
  display: flex;
  flex-direction: column;
  gap: .3rem;
}

.adv-field label {
  font-size: .78rem;
  font-weight: 600;
  color: var(--color-muted);
  text-transform: uppercase;
  letter-spacing: .04em;
}

.adv-field input,
.adv-field select {
  font-size: .88rem;
  padding: .35rem .6rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-bg);
  font-family: inherit;
  transition: border-color .15s;
}
.adv-field input:focus,
.adv-field select:focus {
  outline: none;
  border-color: var(--color-primary);
}

.date-range {
  display: flex;
  align-items: center;
  gap: .4rem;
}
.date-range input { width: 6rem; }

.adv-actions {
  display: flex;
  align-items: center;
  gap: .8rem;
  padding-top: .4rem;
  border-top: 1px solid var(--color-border);
  margin-top: .6rem;
}

.btn-ghost {
  background: none;
  border: 1px solid var(--color-border);
  color: var(--color-muted);
}
.btn-ghost:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.result-breadcrumb {
  display: block;
  font-size: .73rem;
  font-family: ui-sans-serif, system-ui, sans-serif;
  color: var(--color-muted);
  margin-bottom: .3rem;
  line-height: 1.6;
  flex-wrap: wrap;
}
.result-breadcrumb a {
  color: inherit;
  text-decoration: none;
  border-bottom: 1px dotted transparent;
}
.result-breadcrumb a:hover {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}
.result-breadcrumb .sep {
  margin: 0 .3rem;
  color: var(--color-border);
}
.tag--person { border-color: #b0c4de; color: #3a5f8a; }
.tag--geo    { border-color: #c4d4b0; color: #4a6a3a; }
</style>
