<template>
  <div class="container">
    <form class="search-bar" @submit.prevent="currentSearch">
      <input v-model="q" type="text"
        :placeholder="nlMode ? 'Décrivez ce que vous cherchez en langage naturel…' : 'Rechercher dans les archives…'"
        :class="{ 'nl-active': nlMode }"
        autofocus />
      <button class="btn" type="submit">Rechercher</button>
      <button type="button" class="nl-toggle" :class="{ active: nlMode }"
        @click="nlMode = !nlMode" title="Recherche en langage naturel (IA)">✦ IA</button>
      <RouterLink to="/search/advanced" class="adv-link" title="Recherche avancée">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <line x1="4" y1="6" x2="20" y2="6"/><line x1="4" y1="12" x2="14" y2="12"/><line x1="4" y1="18" x2="9" y2="18"/>
          <circle cx="17" cy="15" r="3"/><line x1="19.2" y1="17.2" x2="22" y2="20"/>
        </svg>
        Avancée
      </RouterLink>
    </form>

    <!-- NL interpretation box -->
    <div v-if="nlMode && interpreted" class="nl-interpreted">
      <span class="nl-icon">✦</span>
      <span>{{ interpreted.explanation }}</span>
      <span v-if="interpreted.filters?.length" class="nl-filters">
        — filtres : <code>{{ interpreted.filters.join(' · ') }}</code>
      </span>
    </div>

    <!-- Active filter chips -->
    <div v-if="activeFilters.length" style="display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:.8rem">
      <span
        v-for="f in activeFilters" :key="f.key"
        :class="['chip', { 'chip--excl': f.excl }]"
        @click="removeFilter(f.key)"
      >{{ f.label }} ×</span>
    </div>

    <p v-if="loading" class="loading">Recherche en cours…</p>
    <p v-else-if="error" class="error">{{ error }}</p>

    <div v-else-if="results" class="search-layout">

      <!-- Facets sidebar -->
      <aside class="facets-sidebar">

        <!-- Institution -->
        <div class="facet-group" v-if="facetRepo.length">
          <div class="facet-title">Institution</div>
          <ul>
            <li
              v-for="[val, count] in facetRepo" :key="val"
              :class="{ active: repository === val, excluded: repositoryExcl === val }"
              @click="toggleFacet('repository', val)"
              :title="val"
            >
              <span class="facet-label">{{ val }}</span>
              <span class="facet-count">{{ count }}</span>
              <button class="facet-excl-btn" @click.stop="toggleExclude('repository', val)" title="Exclure">≠</button>
            </li>
          </ul>
        </div>

        <!-- Niveau -->
        <div class="facet-group" v-if="facetLevel.length">
          <div class="facet-title">Niveau</div>
          <ul>
            <li
              v-for="[val, count] in facetLevel" :key="val"
              :class="{ active: level === val, excluded: levelExcl === val }"
              @click="toggleFacet('level', val)"
            >
              <span class="facet-label">{{ val }}</span>
              <span class="facet-count">{{ count }}</span>
              <button class="facet-excl-btn" @click.stop="toggleExclude('level', val)" title="Exclure">≠</button>
            </li>
          </ul>
        </div>

        <!-- Période -->
        <div class="facet-group" v-if="facetCentury.length">
          <div class="facet-title">Période</div>
          <ul>
            <li
              v-for="[val, count] in facetCentury" :key="val"
              :class="{ active: century === val, excluded: centuryExcl === val }"
              @click="toggleFacet('century', val)"
            >
              <span class="facet-label">{{ val }}</span>
              <span class="facet-count">{{ count }}</span>
              <button class="facet-excl-btn" @click.stop="toggleExclude('century', val)" title="Exclure">≠</button>
            </li>
          </ul>
        </div>

        <!-- Genre / forme (gff) -->
        <div class="facet-group" v-if="facetGff.length">
          <div class="facet-title">Genre / forme</div>
          <ul>
            <li
              v-for="[val, count] in facetGff" :key="val"
              :class="{ active: gffNorm === val, excluded: gffNormExcl === val }"
              @click="toggleFacet('gff_norm', val)"
              :title="val"
            >
              <span class="facet-label">{{ val }}</span>
              <span class="facet-count">{{ count }}</span>
              <button class="facet-excl-btn" @click.stop="toggleExclude('gff_norm', val)" title="Exclure">≠</button>
            </li>
          </ul>
        </div>

        <!-- Type de document (tdd) -->
        <div class="facet-group" v-if="facetTdd.length">
          <div class="facet-title">Type de document</div>
          <ul>
            <li
              v-for="[val, count] in facetTdd" :key="val"
              :class="{ active: tddNorm === val, excluded: tddNormExcl === val }"
              @click="toggleFacet('tdd_norm', val)"
              :title="val"
            >
              <span class="facet-label">{{ val }}</span>
              <span class="facet-count">{{ count }}</span>
              <button class="facet-excl-btn" @click.stop="toggleExclude('tdd_norm', val)" title="Exclure">≠</button>
            </li>
          </ul>
        </div>

        <!-- Technique artistique -->
        <div class="facet-group" v-if="facetTechnique.length">
          <div class="facet-title">Technique</div>
          <ul>
            <li
              v-for="[val, count] in facetTechnique" :key="val"
              :class="{ active: techniqueNorm === val, excluded: techniqueNormExcl === val }"
              @click="toggleFacet('technique_norm', val)"
              :title="val"
            >
              <span class="facet-label">{{ val }}</span>
              <span class="facet-count">{{ count }}</span>
              <button class="facet-excl-btn" @click.stop="toggleExclude('technique_norm', val)" title="Exclure">≠</button>
            </li>
          </ul>
        </div>

        <!-- Sujets -->
        <div class="facet-group" v-if="facetSubject.length">
          <div class="facet-title">Sujets</div>
          <ul>
            <li
              v-for="[val, count] in facetSubject" :key="val"
              :class="{ active: subjectNorm === val, excluded: subjectNormExcl === val }"
              @click="toggleFacet('subject_norm', val)"
              :title="val"
            >
              <span class="facet-label">{{ val }}</span>
              <span class="facet-count">{{ count }}</span>
              <button class="facet-excl-btn" @click.stop="toggleExclude('subject_norm', val)" title="Exclure">≠</button>
            </li>
          </ul>
        </div>

        <!-- Lieux -->
        <div class="facet-group" v-if="facetGeo.length">
          <div class="facet-title">Lieux</div>
          <ul>
            <li
              v-for="[val, count] in facetGeo" :key="val"
              :class="{ active: geoNameNorm === val, excluded: geoNameNormExcl === val }"
              @click="toggleFacet('geo_name_norm', val)"
              :title="val"
            >
              <span class="facet-label">{{ val }}</span>
              <span class="facet-count">{{ count }}</span>
              <button class="facet-excl-btn" @click.stop="toggleExclude('geo_name_norm', val)" title="Exclure">≠</button>
            </li>
          </ul>
        </div>

        <!-- Date range (manual) -->
        <div class="facet-group">
          <div class="facet-title">Dates</div>
          <div class="date-range">
            <input v-model.number="dateFrom" type="number" placeholder="de" @change="resetAndSearch" />
            <span>–</span>
            <input v-model.number="dateTo" type="number" placeholder="à" @change="resetAndSearch" />
          </div>
        </div>

      </aside>

      <!-- Results -->
      <div class="search-results">
        <div style="display:flex;align-items:baseline;gap:.8rem;margin-bottom:.8rem;flex-wrap:wrap">
          <p style="font-size:.85rem;color:var(--color-muted);margin:0">
            <template v-if="results.total_hits && results.total_hits > results.total">
              {{ results.total }} entrée{{ results.total !== 1 ? 's' : '' }}
              <span style="opacity:.6">(~{{ results.total_hits.toLocaleString('fr-FR') }} docs)</span>
            </template>
            <template v-else>
              {{ results.total }} résultat{{ results.total !== 1 ? 's' : '' }}
            </template>
            <span v-if="q"> pour « {{ results.query ?? q }} »</span>
          </p>
          <a v-if="searched" :href="currentSearchApiUrl()" target="_blank" class="api-link" title="Voir l'URL de l'API">{ } API</a>
          <button class="btn btn-sm summarize-btn" @click="doSummarize" :disabled="summaryLoading">
            {{ summaryLoading ? 'Résumé en cours…' : '✦ Résumer' }}
          </button>
          <label style="font-size:.8rem;color:var(--color-muted);display:flex;align-items:center;gap:.3rem">
            sur
            <input v-model.number="summaryN" type="number" min="1" max="50"
              style="width:3.5rem;padding:.1rem .3rem;font-size:.8rem" />
            résultats
          </label>
        </div>

        <!-- Summary box -->
        <div v-if="summary" class="summary-box">
          <div class="summary-header">
            <span class="nl-icon">✦</span> Synthèse
            <span style="font-size:.75rem;color:var(--color-muted);margin-left:.5rem">
              ({{ summary.analyzed }} résultats analysés sur {{ summary.total }} au total)
            </span>
          </div>
          <p class="summary-text">{{ summary.summary }}</p>
        </div>

        <ul class="result-list">
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
              <a :href="componentApiUrl(hit)" target="_blank" class="api-link api-link--inline" title="Voir dans l'API">{ }</a>
            </div>
            <div class="meta">
              <span v-if="hit.unitid">{{ hit.unitid }}</span>
              <span v-if="hit.unitid && (hit.date_display || hit.repository)"> &nbsp;·&nbsp; </span>
              <span v-if="hit.date_display">{{ hit.date_display }}</span>
              <span v-if="hit.date_display && hit.repository"> &nbsp;·&nbsp; </span>
              <span v-if="hit.repository">{{ hit.repository }}</span>
              <span v-if="hit._rankingScore != null && q" style="margin-left:.8rem;opacity:.45;font-size:.75rem">
                {{ (hit._rankingScore * 100).toFixed(0) }}%
              </span>
            </div>
            <p v-if="hit.abstract || hit.scope_content" class="excerpt">
              {{ hit.abstract || hit.scope_content }}
            </p>
            <div v-if="hit.subjects?.length || hit.pers_names?.length || hit.geo_names?.length" class="tag-list">
              <span v-for="s in (hit.subjects ?? []).slice(0, 4)" :key="'s'+s" class="tag" @click="addFilter('subject', s)" :title="s">{{ s }}</span>
              <RouterLink v-for="s in (hit.pers_names ?? []).slice(0, 2)" :key="'p'+s" :to="{ name: 'person', params: { name: s } }" class="tag tag--person" :title="s">{{ s }}</RouterLink>
              <span v-for="s in (hit.geo_names ?? []).slice(0, 2)" :key="'g'+s" class="tag tag--geo" :title="s">{{ s }}</span>
            </div>
          </li>
        </ul>

        <div class="pagination">
          <button class="btn btn-sm" :disabled="offset === 0" @click="prevPage">← Précédent</button>
          <span>Page {{ page }} / {{ totalPages }}</span>
          <button class="btn btn-sm" :disabled="offset + limit >= results.total" @click="nextPage">Suivant →</button>
        </div>
      </div>

    </div>
    <p v-else-if="searched" class="empty">Aucun résultat.</p>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { levelLabel } from '../utils/levels'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import ChildrenDensity from '../components/ChildrenDensity.vue'
import { componentPath as cPath, encodeNodeId } from '../router'
import { api, BASE } from '../api'

const route = useRoute()
const router = useRouter()

const q            = ref('')
const level        = ref('')
const dateFrom     = ref(null)
const dateTo       = ref(null)
const lang         = ref('')
const subject      = ref('')
const repository    = ref('')
const repositoryId  = ref('')
const century      = ref('')
const genreFormNorm = ref('')
const gffNorm       = ref('')
const tddNorm       = ref('')
const techniqueNorm = ref('')
const subjectNorm   = ref('')
const geoNameNorm   = ref('')

// Exclusion facets (valeur à exclure des résultats)
const levelExcl        = ref('')
const repositoryExcl   = ref('')
const centuryExcl      = ref('')
const genreFormNormExcl = ref('')
const gffNormExcl       = ref('')
const tddNormExcl       = ref('')
const techniqueNormExcl = ref('')
const subjectNormExcl  = ref('')
const geoNameNormExcl  = ref('')
const limit      = 20
const offset     = ref(0)

const results        = ref(null)
const loading        = ref(false)
const error          = ref(null)
const searched       = ref(false)
const nlMode         = ref(false)
const interpreted    = ref(null)
const summary        = ref(null)
const summaryLoading = ref(false)
const summaryN       = ref(10)

watch(nlMode, () => {
  interpreted.value = null
  results.value = null
  summary.value = null
  searched.value = false
  levelExcl.value = ''; repositoryExcl.value = ''; centuryExcl.value = ''
  genreFormNormExcl.value = ''; gffNormExcl.value = ''; tddNormExcl.value = ''; techniqueNormExcl.value = ''
  subjectNormExcl.value = ''; geoNameNormExcl.value = ''
})

const page       = computed(() => Math.floor(offset.value / limit) + 1)
const totalPages = computed(() => results.value ? Math.ceil(results.value.total / limit) : 1)

// Sort facet entries by count desc, limit to top 10
function topFacet(field, limit = 10) {
  const dist = results.value?.facets?.[field]
  if (!dist) return []
  return Object.entries(dist)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
}

const CENTURY_ORDER = [
  'Ier s.','IIe s.','IIIe s.','IVe s.','Ve s.','VIe s.','VIIe s.','VIIIe s.',
  'IXe s.','Xe s.','XIe s.','XIIe s.','XIIIe s.','XIVe s.','XVe s.','XVIe s.',
  'XVIIe s.','XVIIIe s.','XIXe s.','XXe s.','XXIe s.',
]

const facetRepo      = computed(() => topFacet('repository'))
const facetLevel     = computed(() => topFacet('level', 20))
const facetGff       = computed(() => topFacet('gff_norm', 15))
const facetTdd       = computed(() => topFacet('tdd_norm', 15))
const facetTechnique = computed(() => topFacet('technique_norm', 15))
const facetSubject = computed(() => topFacet('subjects_norm', 10))
const facetGeo     = computed(() => topFacet('geo_names_norm', 10))
const facetCentury = computed(() => {
  const dist = results.value?.facets?.century
  if (!dist) return []
  return Object.entries(dist)
    .sort((a, b) => {
      const ia = CENTURY_ORDER.indexOf(a[0])
      const ib = CENTURY_ORDER.indexOf(b[0])
      return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib)
    })
})

const activeFilters = computed(() => {
  const f = []
  if (subject.value)           f.push({ key: 'subject',              label: `Sujet : ${subject.value}` })
  if (subjectNorm.value)       f.push({ key: 'subject_norm',         label: `Sujet : ${subjectNorm.value}` })
  if (subjectNormExcl.value)   f.push({ key: 'subject_norm_excl',    label: `≠ Sujet : ${subjectNormExcl.value}`, excl: true })
  if (level.value)             f.push({ key: 'level',                label: `Niveau : ${level.value}` })
  if (levelExcl.value)         f.push({ key: 'level_excl',           label: `≠ Niveau : ${levelExcl.value}`, excl: true })
  if (lang.value)              f.push({ key: 'lang',                 label: `Langue : ${lang.value}` })
  if (repository.value)        f.push({ key: 'repository',           label: `Institution : ${repository.value}` })
  if (repositoryId.value)      f.push({ key: 'repository_id',        label: `Institution (id : ${repositoryId.value})` })
  if (repositoryExcl.value)    f.push({ key: 'repository_excl',      label: `≠ Institution : ${repositoryExcl.value}`, excl: true })
  if (century.value)           f.push({ key: 'century',              label: `Période : ${century.value}` })
  if (centuryExcl.value)       f.push({ key: 'century_excl',         label: `≠ Période : ${centuryExcl.value}`, excl: true })
  if (genreFormNorm.value)     f.push({ key: 'genre_form_norm',      label: `Genre/forme : ${genreFormNorm.value}` })
  if (genreFormNormExcl.value) f.push({ key: 'genre_form_norm_excl', label: `≠ Genre/forme : ${genreFormNormExcl.value}`, excl: true })
  if (gffNorm.value)           f.push({ key: 'gff_norm',             label: `Genre/forme : ${gffNorm.value}` })
  if (gffNormExcl.value)       f.push({ key: 'gff_norm_excl',        label: `≠ Genre/forme : ${gffNormExcl.value}`, excl: true })
  if (tddNorm.value)           f.push({ key: 'tdd_norm',             label: `Type doc : ${tddNorm.value}` })
  if (tddNormExcl.value)       f.push({ key: 'tdd_norm_excl',        label: `≠ Type doc : ${tddNormExcl.value}`, excl: true })
  if (techniqueNorm.value)     f.push({ key: 'technique_norm',       label: `Technique : ${techniqueNorm.value}` })
  if (techniqueNormExcl.value) f.push({ key: 'technique_norm_excl',  label: `≠ Technique : ${techniqueNormExcl.value}`, excl: true })
  if (geoNameNorm.value)       f.push({ key: 'geo_name_norm',        label: `Lieu : ${geoNameNorm.value}` })
  if (geoNameNormExcl.value)   f.push({ key: 'geo_name_norm_excl',   label: `≠ Lieu : ${geoNameNormExcl.value}`, excl: true })
  if (dateFrom.value)          f.push({ key: 'dateFrom',             label: `Depuis ${dateFrom.value}` })
  if (dateTo.value)            f.push({ key: 'dateTo',               label: `Jusqu'en ${dateTo.value}` })
  return f
})

function removeFilter(key) {
  if (key === 'subject')              subject.value = ''
  if (key === 'subject_norm')         subjectNorm.value = ''
  if (key === 'subject_norm_excl')    subjectNormExcl.value = ''
  if (key === 'level')                level.value = ''
  if (key === 'level_excl')           levelExcl.value = ''
  if (key === 'lang')                 lang.value = ''
  if (key === 'repository')           repository.value = ''
  if (key === 'repository_id')        repositoryId.value = ''
  if (key === 'repository_excl')      repositoryExcl.value = ''
  if (key === 'century')              century.value = ''
  if (key === 'century_excl')         centuryExcl.value = ''
  if (key === 'genre_form_norm')      genreFormNorm.value = ''
  if (key === 'genre_form_norm_excl') genreFormNormExcl.value = ''
  if (key === 'gff_norm')             gffNorm.value = ''
  if (key === 'gff_norm_excl')        gffNormExcl.value = ''
  if (key === 'tdd_norm')             tddNorm.value = ''
  if (key === 'tdd_norm_excl')        tddNormExcl.value = ''
  if (key === 'technique_norm')       techniqueNorm.value = ''
  if (key === 'technique_norm_excl')  techniqueNormExcl.value = ''
  if (key === 'geo_name_norm')        geoNameNorm.value = ''
  if (key === 'geo_name_norm_excl')   geoNameNormExcl.value = ''
  if (key === 'dateFrom')             dateFrom.value = null
  if (key === 'dateTo')               dateTo.value = null
  offset.value = 0
  runSearch()
}

const _facetInclRefs = () => ({
  level, repository, century,
  genre_form_norm: genreFormNorm, gff_norm: gffNorm, tdd_norm: tddNorm, technique_norm: techniqueNorm,
  subject_norm: subjectNorm, geo_name_norm: geoNameNorm,
})
const _facetExclRefs = () => ({
  level: levelExcl, repository: repositoryExcl, century: centuryExcl,
  genre_form_norm: genreFormNormExcl, gff_norm: gffNormExcl, tdd_norm: tddNormExcl, technique_norm: techniqueNormExcl,
  subject_norm: subjectNormExcl, geo_name_norm: geoNameNormExcl,
})

function toggleFacet(key, val) {
  const incl = _facetInclRefs()[key]
  const excl = _facetExclRefs()[key]
  // Clic ligne : si la valeur est exclue, revenir à neutre ; sinon toggle inclusion
  if (excl.value === val) { excl.value = ''; offset.value = 0; runSearch(); return }
  incl.value = incl.value === val ? '' : val
  offset.value = 0
  runSearch()
}

function toggleExclude(key, val) {
  const incl = _facetInclRefs()[key]
  const excl = _facetExclRefs()[key]
  if (incl.value === val) incl.value = ''  // lever l'inclusion avant d'exclure
  excl.value = excl.value === val ? '' : val
  offset.value = 0
  runSearch()
}

function addFilter(key, value) {
  if (key === 'subject') subject.value = value
  offset.value = 0
  runSearch()
}

function runSearch() {
  summary.value = null
  if (nlMode.value) doNlSearch()
  else doSearch()
}

function currentSearch() {
  offset.value = 0
  runSearch()
}

function resetAndSearch() {
  offset.value = 0
  runSearch()
}

function componentPath(hit) {
  if (hit.depth === 0 && hit.ead_id) return { name: 'fonds', params: { eadId: hit.ead_id } }
  return cPath(hit.node_id)
}

function buildApiUrl(path, params) {
  const url = new URL(BASE + path)
  Object.entries(params).forEach(([k, v]) => {
    if (v !== null && v !== undefined && v !== '') url.searchParams.set(k, v)
  })
  return url.toString()
}

function currentSearchApiUrl() {
  if (nlMode.value) return buildApiUrl('/nlsearch', { q: q.value, limit: 20 })
  return buildApiUrl('/search', { ...currentSearchParams(), limit: 20, offset: offset.value })
}

function componentApiUrl(hit) {
  return buildApiUrl('/component', { node_id: hit.node_id })
}

function currentSearchParams() {
  return {
    q:                    q.value || undefined,
    subject:              subject.value || undefined,
    level:                level.value || undefined,
    level_excl:           levelExcl.value || undefined,
    date_from:            dateFrom.value || undefined,
    date_to:              dateTo.value || undefined,
    lang:                 lang.value || undefined,
    subject_norm:         subjectNorm.value || undefined,
    subject_norm_excl:    subjectNormExcl.value || undefined,
    genre_form_norm:      genreFormNorm.value || undefined,
    genre_form_norm_excl: genreFormNormExcl.value || undefined,
    gff_norm:             gffNorm.value || undefined,
    gff_norm_excl:        gffNormExcl.value || undefined,
    tdd_norm:             tddNorm.value || undefined,
    tdd_norm_excl:        tddNormExcl.value || undefined,
    technique_norm:       techniqueNorm.value || undefined,
    technique_norm_excl:  techniqueNormExcl.value || undefined,
    geo_name_norm:        geoNameNorm.value || undefined,
    geo_name_norm_excl:   geoNameNormExcl.value || undefined,
    repository:           repository.value || undefined,
    repository_id:        repositoryId.value || undefined,
    repository_excl:      repositoryExcl.value || undefined,
    century:              century.value || undefined,
    century_excl:         centuryExcl.value || undefined,
  }
}

async function doSummarize() {
  summaryLoading.value = true
  summary.value = null
  try {
    const params = { ...currentSearchParams(), n: summaryN.value }
    if (nlMode.value && interpreted.value?.q) {
      params.q = interpreted.value.q
      if (interpreted.value.filters?.length)
        params.nl_filters = JSON.stringify(interpreted.value.filters)
    }
    summary.value = await api.summarize(params)
  } catch (e) {
    summary.value = { summary: `(erreur : ${e.message})`, analyzed: 0, total: 0 }
  } finally {
    summaryLoading.value = false
  }
}

async function doNlSearch() {
  loading.value = true
  error.value = null
  searched.value = true
  try {
    const res = await api.nlSearch({ q: q.value, limit, offset: offset.value })
    results.value = res
    interpreted.value = res.interpreted ?? null
    router.replace({ query: { q: q.value || undefined, nl: '1' } })
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function doSearch() {
  interpreted.value = null
  loading.value = true
  error.value = null
  searched.value = true
  try {
    results.value = await api.search({
      ...currentSearchParams(),
      limit,
      offset: offset.value,
    })
    router.replace({ query: currentSearchParams() })
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function prevPage() { offset.value -= limit; runSearch() }
function nextPage() { offset.value += limit; runSearch() }

function applyRouteQuery(rq) {
  if (rq.nl === '1')              nlMode.value = true
  if (rq.q)                       q.value = rq.q
  if (rq.subject)                 subject.value = rq.subject
  if (rq.level)                   level.value = rq.level
  if (rq.level_excl)              levelExcl.value = rq.level_excl
  if (rq.lang)                    lang.value = rq.lang
  if (rq.date_from)               dateFrom.value = parseInt(rq.date_from)
  if (rq.date_to)                 dateTo.value = parseInt(rq.date_to)
  if (rq.subject_norm)            subjectNorm.value = rq.subject_norm
  if (rq.subject_norm_excl)       subjectNormExcl.value = rq.subject_norm_excl
  if (rq.genre_form_norm)         genreFormNorm.value = rq.genre_form_norm
  if (rq.genre_form_norm_excl)    genreFormNormExcl.value = rq.genre_form_norm_excl
  if (rq.gff_norm)                gffNorm.value = rq.gff_norm
  if (rq.gff_norm_excl)           gffNormExcl.value = rq.gff_norm_excl
  if (rq.tdd_norm)                tddNorm.value = rq.tdd_norm
  if (rq.tdd_norm_excl)           tddNormExcl.value = rq.tdd_norm_excl
  if (rq.technique_norm)          techniqueNorm.value = rq.technique_norm
  if (rq.technique_norm_excl)     techniqueNormExcl.value = rq.technique_norm_excl
  if (rq.geo_name_norm)           geoNameNorm.value = rq.geo_name_norm
  if (rq.geo_name_norm_excl)      geoNameNormExcl.value = rq.geo_name_norm_excl
  if (rq.repository)              repository.value = rq.repository
  if (rq.repository_id)           repositoryId.value = rq.repository_id
  if (rq.repository_excl)         repositoryExcl.value = rq.repository_excl
  if (rq.century)                 century.value = rq.century
  if (rq.century_excl)            centuryExcl.value = rq.century_excl
  // Params issus des tags ComponentView (texte libre injecté dans q si pas de q ni subject)
  const textTerm = rq.pers_name || rq.geo_name || rq.genre_form || rq.corp_name
  if (textTerm && !rq.q) q.value = textTerm
}

onMounted(() => {
  applyRouteQuery(route.query)
  runSearch()
})

// Triggered by external navigation (tag clicks, header search bar)
watch(() => route.query, (rq) => {
  // Ignore updates caused by our own router.replace({q:...}) inside doSearch
  const externalParams = ['subject', 'pers_name', 'geo_name', 'genre_form', 'corp_name',
                          'subject_norm', 'subject_norm_excl', 'genre_form_norm', 'genre_form_norm_excl',
                          'gff_norm', 'gff_norm_excl', 'tdd_norm', 'tdd_norm_excl',
                          'technique_norm', 'technique_norm_excl',
                          'geo_name_norm', 'geo_name_norm_excl', 'repository', 'repository_id',
                          'repository_excl', 'century', 'century_excl', 'level', 'level_excl',
                          'lang', 'date_from', 'date_to']
  const hasExternal = externalParams.some(k => k in rq)
  const qChanged = (rq.q || '') !== q.value
  if (!hasExternal && !qChanged) return
  // Reset all filters before re-applying from URL
  q.value = ''; subject.value = ''; lang.value = ''; dateFrom.value = null; dateTo.value = null
  level.value = ''; levelExcl.value = ''
  repository.value = ''; repositoryId.value = ''; repositoryExcl.value = ''
  century.value = ''; centuryExcl.value = ''
  subjectNorm.value = ''; subjectNormExcl.value = ''
  genreFormNorm.value = ''; genreFormNormExcl.value = ''
  gffNorm.value = ''; gffNormExcl.value = ''
  tddNorm.value = ''; tddNormExcl.value = ''
  techniqueNorm.value = ''; techniqueNormExcl.value = ''
  geoNameNorm.value = ''; geoNameNormExcl.value = ''
  offset.value = 0
  applyRouteQuery(rq)
  runSearch()
})
</script>

<style scoped>
.api-link {
  font-size: .72rem;
  font-family: monospace;
  color: var(--color-muted);
  opacity: .5;
  text-decoration: none;
  border: 1px solid currentColor;
  border-radius: 3px;
  padding: .1rem .35rem;
  transition: opacity .15s;
  white-space: nowrap;
}
.api-link:hover { opacity: 1; color: #2563eb; }
.api-link--inline {
  font-size: .65rem;
  padding: .05rem .25rem;
  margin-left: .4rem;
  vertical-align: middle;
}

.summarize-btn {
  font-size: .8rem;
  padding: .25rem .6rem;
  color: #5b21b6;
  border-color: #ddd6fe;
  background: #f5f0ff;
}
.summarize-btn:hover:not(:disabled) { background: #ede9fe; border-color: #7c3aed; }
.summarize-btn:disabled { opacity: .6; cursor: default; }

.summary-box {
  background: #f5f0ff;
  border: 1px solid #ddd6fe;
  border-radius: var(--radius);
  padding: .8rem 1rem;
  margin-bottom: 1rem;
}
.summary-header {
  font-size: .78rem;
  font-weight: 600;
  color: #5b21b6;
  margin-bottom: .5rem;
  display: flex;
  align-items: baseline;
  gap: .3rem;
}
.summary-text {
  font-size: .88rem;
  line-height: 1.6;
  color: var(--color-text);
  margin: 0;
}

.nl-toggle {
  display: inline-flex;
  align-items: center;
  gap: .25rem;
  font-size: .82rem;
  font-weight: 600;
  color: var(--color-muted);
  background: none;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: .3rem .55rem;
  cursor: pointer;
  white-space: nowrap;
  transition: color .15s, border-color .15s, background .15s;
}
.nl-toggle:hover { color: #7c3aed; border-color: #7c3aed; }
.nl-toggle.active { color: #7c3aed; border-color: #7c3aed; background: #f5f0ff; }

input.nl-active { border-color: #7c3aed; box-shadow: 0 0 0 2px #ede9fe; }

.nl-interpreted {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: .4rem;
  font-size: .82rem;
  color: #5b21b6;
  background: #f5f0ff;
  border: 1px solid #ddd6fe;
  border-radius: var(--radius);
  padding: .45rem .7rem;
  margin-bottom: .8rem;
}
.nl-icon { font-size: .9rem; flex-shrink: 0; }
.nl-filters { color: var(--color-muted); }
.nl-filters code { font-size: .78rem; background: #ede9fe; padding: .1rem .35rem; border-radius: 4px; }

.adv-link {
  display: inline-flex;
  align-items: center;
  gap: .3rem;
  font-size: .82rem;
  color: var(--color-muted);
  white-space: nowrap;
  text-decoration: none;
  padding: .3rem .5rem;
  border-radius: var(--radius);
  transition: color .15s;
}
.adv-link:hover { color: var(--color-primary); text-decoration: none; }

.search-layout {
  display: flex;
  gap: 1.5rem;
  align-items: flex-start;
}

.facets-sidebar {
  flex: 0 0 200px;
  min-width: 0;
}

.search-results {
  flex: 1;
  min-width: 0;
}

.facet-group {
  margin-bottom: 1.2rem;
}

.facet-title {
  font-size: .75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--color-muted);
  margin-bottom: .4rem;
  padding-bottom: .25rem;
  border-bottom: 1px solid var(--color-border);
}

.facet-group ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.facet-group li {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: .4rem;
  padding: .18rem .3rem;
  border-radius: 4px;
  cursor: pointer;
  font-size: .82rem;
  line-height: 1.3;
}

.facet-group li:hover {
  background: var(--color-surface-alt, #f5f5f5);
}

.facet-group li.active {
  background: var(--color-primary-light, #e8f0fe);
  color: var(--color-primary);
  font-weight: 600;
}

.facet-group li.excluded {
  background: #fee2e2;
  color: #b91c1c;
  font-weight: 600;
}

.facet-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.facet-count {
  flex-shrink: 0;
  font-size: .75rem;
  color: var(--color-muted);
  background: var(--color-border);
  border-radius: 10px;
  padding: 0 .4rem;
  line-height: 1.4;
}

.facet-group li.active .facet-count {
  background: var(--color-primary);
  color: #fff;
}

.facet-group li.excluded .facet-count {
  background: #fca5a5;
  color: #7f1d1d;
}

.facet-excl-btn {
  display: none;
  margin-left: auto;
  flex-shrink: 0;
  background: none;
  border: 1px solid #fca5a5;
  border-radius: 3px;
  color: #ef4444;
  font-size: .72rem;
  line-height: 1;
  padding: .05rem .25rem;
  cursor: pointer;
  transition: background .12s, color .12s;
}
.facet-group li:hover .facet-excl-btn,
.facet-group li.excluded .facet-excl-btn { display: inline-block; }
.facet-excl-btn:hover { background: #fee2e2; color: #b91c1c; }

.chip--excl {
  background: #fee2e2;
  color: #b91c1c;
  border-color: #fca5a5;
}

.date-range {
  display: flex;
  align-items: center;
  gap: .3rem;
}

.date-range input {
  width: 5rem;
}

.tag--person { border-color: #b0c4de; color: #3a5f8a; }
.tag--person:hover { border-color: var(--color-primary); color: var(--color-primary); }
.tag--geo { border-color: #c4d4b0; color: #4a6a3a; }
.tag--geo:hover { border-color: #4a6a3a; color: #4a6a3a; }

.result-breadcrumb {
  display: block;
  font-size: .73rem;
  font-family: ui-sans-serif, system-ui, sans-serif;
  color: var(--color-muted);
  margin-bottom: .3rem;
  line-height: 1.6;
  opacity: .8;
}

.result-breadcrumb a {
  color: inherit;
  text-decoration: none;
  border-bottom: 1px dotted transparent;
  transition: color .12s, border-color .12s;
}

.result-breadcrumb a:hover {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
  text-decoration: none;
}

.result-breadcrumb .sep {
  margin: 0 .3rem;
  color: var(--color-border);
  font-size: .8em;
  vertical-align: .05em;
}
</style>
