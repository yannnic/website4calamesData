<template>
  <div class="tree-node">
    <div class="tree-row" :class="{ 'tree-row--open': open }">
      <button v-if="childCount > 0" class="tree-toggle" :title="open ? 'Replier' : 'Déplier les enfants'"
              @click="open = !open">{{ open ? '▾' : '▸' }}</button>
      <span v-else class="tree-leaf" />
      <span class="level-badge" :class="`level-${doc.level || 'fonds'}`" style="font-size:.65rem">{{ levelLabel(doc.level || 'fonds') }}</span>
      <ChildrenDensity :count="childCount" style="margin-right:.3rem;opacity:.7" />
      <RouterLink :to="nodeLink" class="node-title">{{ doc.title }}</RouterLink>
      <span v-if="doc.date_display" class="node-date">{{ doc.date_display }}</span>
      <button class="desc-toggle" :class="{ active: showDesc }"
              :title="showDesc ? 'Masquer la description' : 'Afficher la description'"
              @click="toggleDesc">ⓘ</button>
    </div>

    <ComponentSummary v-if="showDesc" :doc="desc" :loading="descLoading" :error="descError" />

    <div v-if="open" class="tree-children">
      <p v-if="loadingChildren" class="loading" style="padding:.3rem .8rem;font-size:.82rem">Chargement…</p>
      <p v-else-if="childError" class="error" style="font-size:.82rem">{{ childError }}</p>
      <ComponentTree
        v-for="child in children"
        :key="child.node_id"
        :doc="child"
        :show-description="expandAll"
        :expand-all="expandAll"
        :subtree="subtree"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { levelLabel } from '../utils/levels'
import { componentPath } from '../router'
import { api } from '../api'
import ChildrenDensity from './ChildrenDensity.vue'
import ComponentSummary from './ComponentSummary.vue'

const props = defineProps({
  doc:             { type: Object,  required: true },   // ligne de /children ou /subtree
  showDescription: { type: Boolean, default: false },
  expandAll:       { type: Boolean, default: false },   // sous-arbre entier déplié
  subtree:         { type: Object,  default: null },    // { parent_id: [enfants] } (mode « tout déplier »)
})

const childCount = computed(() => props.doc.children_count ?? 0)
const nodeLink = computed(() =>
  props.doc.depth === 0
    ? { name: 'fonds', params: { eadId: props.doc.ead_id } }
    : componentPath(props.doc.node_id))

// --- Description (ⓘ) : celle du document reçu s'il la contient, sinon chargée à la demande
const showDesc    = ref(props.showDescription || props.expandAll)
const fetchedDoc  = ref(null)
const descLoading = ref(false)
const descError   = ref(null)
const desc = computed(() => fetchedDoc.value ?? ('scope_content' in props.doc ? props.doc : null))

async function loadDesc() {
  if (desc.value || descLoading.value) return
  descLoading.value = true
  descError.value = null
  try {
    fetchedDoc.value = await api.getComponent(props.doc.node_id)
  } catch (e) {
    descError.value = e.message
  } finally {
    descLoading.value = false
  }
}

function toggleDesc() {
  showDesc.value = !showDesc.value
}

watch(showDesc, (v) => { if (v) loadDesc() }, { immediate: true })
watch(() => props.showDescription, (v) => { showDesc.value = v || props.expandAll })

// --- Enfants : du sous-arbre déjà chargé, sinon /children à l'ouverture
const open            = ref(props.expandAll)
const fetchedChildren = ref([])
const loadingChildren = ref(false)
const childError      = ref(null)
const children = computed(() => props.subtree?.[props.doc.node_id] ?? fetchedChildren.value)

async function loadChildren() {
  if (props.subtree || fetchedChildren.value.length) return
  loadingChildren.value = true
  childError.value = null
  try {
    fetchedChildren.value = await api.getChildren(props.doc.node_id)
  } catch (e) {
    childError.value = e.message
  } finally {
    loadingChildren.value = false
  }
}

watch(open, (v) => { if (v) loadChildren() }, { immediate: true })
watch(() => props.expandAll, (v) => { open.value = v; showDesc.value = v || props.showDescription })
</script>

<style scoped>
.tree-node { border-left: 2px solid var(--color-border); padding-left: .6rem; margin-top: .3rem; }
.tree-row {
  display: flex; align-items: baseline; gap: .3rem;
  padding: .3rem .4rem; border-radius: var(--radius);
}
.tree-row:hover { background: rgba(26,74,122,.06); }
.tree-row--open > .node-title { color: var(--color-primary); }
.tree-toggle, .tree-leaf { width: 1rem; flex-shrink: 0; }
.tree-toggle {
  background: none; border: none; padding: 0; cursor: pointer;
  color: var(--color-muted); font-size: .8rem; line-height: 1;
}
.tree-toggle:hover { color: var(--color-primary); }
.node-title { font-size: .92rem; }
.node-date  { font-size: .76rem; color: var(--color-muted); }
.desc-toggle {
  margin-left: auto; flex-shrink: 0;
  background: none; border: none; padding: 0 .2rem; cursor: pointer;
  color: var(--color-border); font-size: .85rem; line-height: 1;
}
.tree-row:hover .desc-toggle { color: var(--color-muted); }
.desc-toggle:hover, .desc-toggle.active { color: var(--color-primary) !important; }
</style>
