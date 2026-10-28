<template>
  <div class="container">
    <p v-if="loading" class="loading">Chargement…</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <template v-else-if="fonds">
      <RouterLink v-if="lastResultsUrl" :to="lastResultsUrl" class="back-link">← Retour aux résultats</RouterLink>
      <ResultNav :node-id="fonds.node_id" />
      <!-- Titre -->
      <h1><span v-if="fonds.unitid" class="cote">{{ fonds.unitid }}</span>{{ fonds.title }}</h1>
      <div class="meta" style="margin-bottom:1.2rem;font-size:.9rem;color:var(--color-muted)">
        <span v-if="fonds.date_display">{{ fonds.date_display }}<span v-if="dateOrigin(fonds)" class="origin-badge">{{ dateOrigin(fonds) }}</span> &nbsp;·&nbsp; </span>
        <span>{{ fonds.repository }}</span> <span v-if="isInheritedField(fonds, 'repository')" class="origin-badge">héritée</span>
      </div>
      <TestFileComment :comment="fonds.file_comment" />

      <div style="display:grid;grid-template-columns:1fr 340px;gap:1.5rem;align-items:start">
        <!-- Arbre de navigation -->
        <section>
          <!-- Comme sur la page d'un composant : dans la colonne principale, avant les enfants -->
          <RawEad :node-id="fonds.node_id" :has-children="(fonds.children_count ?? 0) > 0"
                  style="margin:0 0 1.4rem" />
          <form class="fonds-search" @submit.prevent="searchInFonds">
            <input v-model="fondsQuery" type="search" placeholder="Rechercher dans ce fonds…" />
            <button class="btn btn-sm" type="submit">Rechercher</button>
          </form>
          <h2 style="margin-bottom:.8rem">Plan du fonds</h2>
          <ChildrenTree :node-id="fonds.node_id" :children-count="fonds.children_count ?? 0"
                        :descendants-count="fonds.descendants_count ?? null" />
        </section>

        <!-- Panneau de description -->
        <aside class="detail-panel">
          <h2 style="margin-bottom:.8rem">Description</h2>
          <dl>
            <template v-if="fonds.abstract">
              <dt>Présentation</dt>
              <dd>{{ fonds.abstract }}</dd>
            </template>
            <template v-if="fonds.scope_content">
              <dt>Présentation du contenu</dt>
              <dd style="white-space:pre-line">{{ fonds.scope_content }}</dd>
            </template>
            <template v-if="fonds.biography">
              <dt>Biographie ou histoire</dt>
              <dd style="white-space:pre-line">{{ fonds.biography }}</dd>
            </template>
            <template v-if="fonds.creators?.length">
              <dt>Créateur(s)</dt>
              <dd>
                <div v-for="c in fonds.creators" :key="c.name">
                  {{ c.name }}<span v-if="c.role" style="color:var(--color-muted)"> ({{ roleLabel(c.role) }})</span>
                </div>
              </dd>
            </template>
            <template v-if="fonds.extents?.length">
              <dt>Importance</dt>
              <dd>{{ fonds.extents.join(' — ') }}</dd>
            </template>
            <template v-if="fonds.languages?.length">
              <dt>Langues</dt>
              <dd>{{ fonds.languages.map(langLabel).join(', ') }} <span v-if="isInheritedField(fonds, 'languages')" class="origin-badge">héritée</span></dd>
            </template>
            <template v-if="fonds.access_restrict">
              <dt>Accès</dt>
              <dd>{{ fonds.access_restrict }} <span v-if="isInheritedField(fonds, 'access_restrict')" class="origin-badge">héritée</span></dd>
            </template>
          </dl>
          <ExtraDescription :doc="fonds" />

          <template v-if="fonds.subjects?.length">
            <h3>Sujets</h3>
            <div class="tag-list">
              <RouterLink
                v-for="s in fonds.subjects" :key="s"
                :to="{ path: '/search', query: { subject: s } }"
                class="tag" :class="{ 'tag--inherited': isInheritedTerm(fonds, 'subjects', s) }"
              >{{ s }}</RouterLink>
            </div>
          </template>

          <template v-if="fonds.geo_names?.length">
            <h3>Lieux</h3>
            <div class="tag-list">
              <RouterLink
                v-for="g in fonds.geo_names" :key="g"
                :to="{ path: '/search', query: { geo_name: g } }"
                class="tag" :class="{ 'tag--inherited': isInheritedTerm(fonds, 'geo_names', g) }"
              >{{ g }}</RouterLink>
            </div>
          </template>

          <template v-if="fonds.pers_names?.length">
            <h3>Personnes</h3>
            <div class="tag-list">
              <RouterLink
                v-for="p in fonds.pers_names" :key="p"
                :to="{ path: '/search', query: { pers_name: p } }"
                class="tag" :class="{ 'tag--inherited': isInheritedTerm(fonds, 'pers_names', p) }"
              >{{ p }}</RouterLink>
            </div>
          </template>

          <template v-if="fonds.corp_names?.length">
            <h3>Collectivités</h3>
            <div class="tag-list">
              <RouterLink
                v-for="c in fonds.corp_names" :key="c"
                :to="{ path: '/search', query: { corp_name: c } }"
                class="tag" :class="{ 'tag--inherited': isInheritedTerm(fonds, 'corp_names', c) }"
              >{{ c }}</RouterLink>
            </div>
          </template>

          <template v-if="fonds.fam_names?.length">
            <h3>Familles</h3>
            <div class="tag-list">
              <RouterLink
                v-for="f in fonds.fam_names" :key="f"
                :to="{ path: '/search', query: { q: f } }"
                class="tag" :class="{ 'tag--inherited': isInheritedTerm(fonds, 'fam_names', f) }"
              >{{ f }}</RouterLink>
            </div>
          </template>

          <template v-if="fonds.genre_forms?.length">
            <h3>Genre/forme</h3>
            <div class="tag-list">
              <RouterLink
                v-for="g in fonds.genre_forms" :key="g"
                :to="{ path: '/search', query: { genre_form: g } }"
                class="tag" :class="{ 'tag--inherited': isInheritedTerm(fonds, 'genre_forms', g) }"
              >{{ g }}</RouterLink>
            </div>
          </template>

          <template v-if="fonds.work_titles?.length">
            <h3>Titres d'œuvres</h3>
            <div class="tag-list">
              <RouterLink
                v-for="t in fonds.work_titles" :key="t"
                :to="{ path: '/search', query: { work_title: t } }"
                class="tag" :class="{ 'tag--inherited': isInheritedTerm(fonds, 'work_titles', t) }"
              >{{ t }}</RouterLink>
            </div>
          </template>
          <template v-if="fonds.functions?.length">
            <h3>Fonctions</h3>
            <div class="tag-list">
              <RouterLink
                v-for="t in fonds.functions" :key="t"
                :to="{ path: '/search', query: { function: t } }"
                class="tag" :class="{ 'tag--inherited': isInheritedTerm(fonds, 'functions', t) }"
              >{{ t }}</RouterLink>
            </div>
          </template>
          <template v-if="fonds.provenance?.length">
            <h3>Provenance</h3>
            <div class="tag-list">
              <RouterLink
                v-for="t in fonds.provenance" :key="t"
                :to="{ path: '/search', query: { provenance: t } }"
                class="tag" :class="{ 'tag--inherited': isInheritedTerm(fonds, 'provenance', t) }"
              >{{ t }}</RouterLink>
            </div>
          </template>
        </aside>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { api } from '../api'
import ChildrenTree from '../components/ChildrenTree.vue'
import TestFileComment from '../components/TestFileComment.vue'
import RawEad from '../components/RawEad.vue'
import ExtraDescription from '../components/ExtraDescription.vue'
import ResultNav from '../components/ResultNav.vue'
import { loadResults } from '../utils/results'
import { roleLabel, langLabel } from '../utils/labels'
import { isInheritedTerm, isInheritedField, dateOrigin } from '../utils/origin'

const route = useRoute()
const router = useRouter()
// La dernière liste de résultats (et non la page précédente)
const lastResultsUrl = computed(() => (route.params.eadId, loadResults().url))

// Recherche restreinte au fonds et aux fichiers qui y sont rattachés (filtre ead_id)
const fondsQuery = ref('')
function searchInFonds() {
  if (!fonds.value) return
  router.push({ path: '/search', query: { q: fondsQuery.value.trim() || undefined, ead_id: fonds.value.ead_id } })
}
const fonds = ref(null)
const loading = ref(true)
const error = ref(null)

onMounted(async () => {
  try {
    fonds.value = await api.getFonds(route.params.eadId)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.back-link { display: inline-block; font-size: .85rem; margin-bottom: .6rem; }
.fonds-search { display: flex; gap: .4rem; margin-bottom: 1rem; }
.fonds-search input { flex: 1; padding: .35rem .5rem; border: 1px solid var(--color-border); border-radius: var(--radius); }
</style>
