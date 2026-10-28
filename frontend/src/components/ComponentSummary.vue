<template>
  <!-- Description compacte d'un composant, dépliée dans l'arbre sous son titre. -->
  <div class="cs">
    <p v-if="loading" class="cs-muted">Chargement…</p>
    <p v-else-if="error" class="cs-error">{{ error }}</p>
    <template v-else-if="doc">
      <div v-if="meta.length" class="cs-meta">{{ meta.join(' · ') }}</div>
      <p v-if="text" class="cs-text">{{ shortText }}<RouterLink
          v-if="text.length > MAX_TEXT" :to="link" class="cs-more"> lire la suite</RouterLink></p>
      <p v-if="!meta.length && !text" class="cs-muted">Pas de description à ce niveau.</p>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { componentPath } from '../router'

// Au-delà, le texte est coupé : la fiche du composant le donne en entier.
const MAX_TEXT = 500

const props = defineProps({
  doc:     { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error:   { type: String, default: null },
})

const meta = computed(() => {
  const d = props.doc
  if (!d) return []
  return [d.date_display, ...(d.extents ?? []), ...(d.phys_facets ?? [])].filter(Boolean)
})
const text      = computed(() => props.doc?.abstract || props.doc?.scope_content || props.doc?.biography || '')
const shortText = computed(() => text.value.length > MAX_TEXT ? text.value.slice(0, MAX_TEXT).trimEnd() + '…' : text.value)
const link      = computed(() => componentPath(props.doc.node_id))
</script>

<style scoped>
.cs {
  margin: .1rem 0 .4rem 1.6rem;
  padding: .35rem .6rem;
  border-left: 2px solid #e6dcc8;
  background: #fbf9f4;
  font-size: .82rem;
  line-height: 1.5;
}
.cs-meta  { color: var(--color-muted); font-size: .78rem; }
.cs-text  { margin: .2rem 0 0; white-space: pre-line; }
.cs-more  { font-size: .78rem; }
.cs-muted { color: var(--color-muted); font-style: italic; margin: 0; }
.cs-error { color: #c0392b; margin: 0; }
</style>
