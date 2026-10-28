<template>
  <div class="container">
    <p v-if="loading" class="loading">Chargement…</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <template v-else-if="fonds">
      <!-- Titre -->
      <h1><span v-if="fonds.unitid" class="cote">{{ fonds.unitid }}</span>{{ fonds.title }}</h1>
      <div class="meta" style="margin-bottom:1.2rem;font-size:.9rem;color:var(--color-muted)">
        <span v-if="fonds.date_display">{{ fonds.date_display }} &nbsp;·&nbsp; </span>
        <span>{{ fonds.repository }}</span>
      </div>
      <TestFileComment :comment="fonds.file_comment" />

      <div style="display:grid;grid-template-columns:1fr 340px;gap:1.5rem;align-items:start">
        <!-- Arbre de navigation -->
        <section>
          <!-- Comme sur la page d'un composant : dans la colonne principale, avant les enfants -->
          <RawEad :node-id="fonds.node_id" :has-children="(fonds.children_count ?? 0) > 0"
                  style="margin:0 0 1.4rem" />
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
            <template v-if="fonds.creators?.length">
              <dt>Créateur(s)</dt>
              <dd>
                <div v-for="c in fonds.creators" :key="c.name">
                  {{ c.name }}<span v-if="c.role" style="color:var(--color-muted)"> ({{ c.role }})</span>
                </div>
              </dd>
            </template>
            <template v-if="fonds.extents?.length">
              <dt>Importance</dt>
              <dd>{{ fonds.extents.join(' — ') }}</dd>
            </template>
            <template v-if="fonds.languages?.length">
              <dt>Langues</dt>
              <dd>{{ fonds.languages.join(', ') }}</dd>
            </template>
            <template v-if="fonds.access_restrict">
              <dt>Accès</dt>
              <dd>{{ fonds.access_restrict }}</dd>
            </template>
          </dl>

          <template v-if="fonds.subjects?.length">
            <h3>Sujets</h3>
            <div class="tag-list">
              <RouterLink
                v-for="s in fonds.subjects" :key="s"
                :to="{ path: '/search', query: { subject: s } }"
                class="tag"
              >{{ s }}</RouterLink>
            </div>
          </template>

          <template v-if="fonds.geo_names?.length">
            <h3>Lieux</h3>
            <div class="tag-list">
              <RouterLink
                v-for="g in fonds.geo_names" :key="g"
                :to="{ path: '/search', query: { geo_name: g } }"
                class="tag"
              >{{ g }}</RouterLink>
            </div>
          </template>

          <template v-if="fonds.pers_names?.length">
            <h3>Personnes</h3>
            <div class="tag-list">
              <RouterLink
                v-for="p in fonds.pers_names" :key="p"
                :to="{ path: '/search', query: { pers_name: p } }"
                class="tag"
              >{{ p }}</RouterLink>
            </div>
          </template>

          <template v-if="fonds.corp_names?.length">
            <h3>Collectivités</h3>
            <div class="tag-list">
              <RouterLink
                v-for="c in fonds.corp_names" :key="c"
                :to="{ path: '/search', query: { corp_name: c } }"
                class="tag"
              >{{ c }}</RouterLink>
            </div>
          </template>

          <template v-if="fonds.fam_names?.length">
            <h3>Familles</h3>
            <div class="tag-list">
              <RouterLink
                v-for="f in fonds.fam_names" :key="f"
                :to="{ path: '/search', query: { q: f } }"
                class="tag"
              >{{ f }}</RouterLink>
            </div>
          </template>

          <template v-if="fonds.genre_forms?.length">
            <h3>Genre/forme</h3>
            <div class="tag-list">
              <RouterLink
                v-for="g in fonds.genre_forms" :key="g"
                :to="{ path: '/search', query: { genre_form: g } }"
                class="tag"
              >{{ g }}</RouterLink>
            </div>
          </template>
        </aside>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { api } from '../api'
import ChildrenTree from '../components/ChildrenTree.vue'
import TestFileComment from '../components/TestFileComment.vue'
import RawEad from '../components/RawEad.vue'

const route = useRoute()
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
