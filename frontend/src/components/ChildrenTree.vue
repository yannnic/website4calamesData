<template>
  <!-- Enfants d'un niveau de l'arbre EAD, avec le dépliage des descriptions
       (règles et seuils : utils/expand.js). -->
  <div>
    <div class="ct-controls">
      <button :class="{ active: mode === 'titles' }" @click="setMode('titles')">Titres</button>
      <button :class="{ active: mode === 'descriptions' }" :disabled="!canDescribe"
              :title="canDescribe ? 'Déplier la description de chaque enfant' : describeReason"
              @click="setMode('descriptions')">Descriptions des enfants</button>
      <button :class="{ active: mode === 'all' }" :disabled="!canExpandAll"
              :title="canExpandAll ? 'Déplier tout le sous-arbre, descriptions comprises' : expandAllReason"
              @click="setMode('all')">Tout déplier</button>
      <span v-if="note" class="ct-note">{{ note }}</span>
    </div>

    <p v-if="loading" class="loading" style="font-size:.85rem">Chargement…</p>
    <p v-else-if="error" class="error" style="font-size:.85rem">{{ error }}</p>
    <ComponentTree
      v-for="child in children"
      :key="child.node_id"
      :doc="child"
      :show-description="mode !== 'titles'"
      :expand-all="mode === 'all'"
      :subtree="mode === 'all' ? subtree : null"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { api } from '../api'
import { EXPAND_CHILDREN_MAX, EXPAND_SUBTREE_MAX } from '../utils/expand'
import ComponentTree from './ComponentTree.vue'

const props = defineProps({
  nodeId:           { type: String, required: true },
  childrenCount:    { type: Number, default: 0 },
  descendantsCount: { type: Number, default: null },   // null : inconnu
  initialChildren:  { type: Array,  default: null },   // déjà chargés par la page
})

const fmt = (n) => n.toLocaleString('fr-FR')

const canDescribe  = computed(() => props.childrenCount <= EXPAND_CHILDREN_MAX)
const canExpandAll = computed(() =>
  props.descendantsCount !== null && props.descendantsCount <= EXPAND_SUBTREE_MAX)
const describeReason = computed(() =>
  `${fmt(props.childrenCount)} enfants : trop pour tout afficher (max ${EXPAND_CHILDREN_MAX}). ` +
  'Dépliez les descriptions une à une avec ⓘ.')
const expandAllReason = computed(() =>
  props.descendantsCount === null
    ? 'Taille du sous-arbre inconnue.'
    : `${fmt(props.descendantsCount)} composants dans ce sous-arbre : trop lourd à tout déplier ` +
      `(max ${EXPAND_SUBTREE_MAX}). Ouvrez-le niveau par niveau.`)
// Ce qui n'est pas proposé, et pourquoi (le bouton désactivé le dit aussi au survol).
const note = computed(() => {
  if (!canDescribe.value) return describeReason.value
  if (!canExpandAll.value && props.descendantsCount !== null) {
    return `Tout déplier : ${fmt(props.descendantsCount)} composants, au-delà de ${EXPAND_SUBTREE_MAX}.`
  }
  return ''
})

const mode     = ref('titles')
const children = ref(props.initialChildren ?? [])
const subtree  = ref(null)      // { parent_id: [enfants] }
const loading  = ref(false)
const error    = ref(null)

async function run(fn) {
  loading.value = true
  error.value = null
  try {
    await fn()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function setMode(m) {
  if (m === 'descriptions' && !('scope_content' in (children.value[0] ?? {}))) {
    await run(async () => { children.value = await api.getChildren(props.nodeId, true) })
  } else if (m === 'all' && !subtree.value) {
    await run(async () => {
      const { nodes } = await api.getSubtree(props.nodeId, EXPAND_SUBTREE_MAX)
      const byParent = {}
      for (const n of nodes) (byParent[n.parent_id] ??= []).push(n)
      subtree.value = byParent
      children.value = byParent[props.nodeId] ?? []
    })
  }
  if (!error.value) mode.value = m
}

async function reset() {
  mode.value = 'titles'
  subtree.value = null
  children.value = props.initialChildren ?? []
  if (!props.initialChildren) await run(async () => { children.value = await api.getChildren(props.nodeId) })
}

watch(() => props.nodeId, reset, { immediate: true })
watch(() => props.initialChildren, (v) => { if (v && mode.value === 'titles') children.value = v })
</script>

<style scoped>
.ct-controls { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem; margin-bottom: .6rem; }
.ct-controls button {
  font-size: .78rem; padding: .2rem .6rem; cursor: pointer;
  background: var(--color-surface); color: var(--color-primary);
  border: 1px solid var(--color-border); border-radius: 999px;
}
.ct-controls button.active { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
.ct-controls button:disabled { color: var(--color-muted); opacity: .55; cursor: not-allowed; }
.ct-note { font-size: .75rem; color: var(--color-muted); }
</style>
