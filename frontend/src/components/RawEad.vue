<template>
  <!-- XML EAD natif d'un composant, chargé à l'ouverture. -->
  <details :key="nodeId" class="raw-ead" @toggle="onToggle">
    <summary>Voir le XML EAD natif</summary>
    <label v-if="hasChildren" class="raw-children">
      <input v-model="withChildren" type="checkbox" @change="load" />
      inclure les composants enfants
    </label>
    <div v-if="loading" class="raw-loading">Chargement…</div>
    <div v-else-if="error" class="raw-error">{{ error }}</div>
    <pre v-else-if="xml" class="raw-pre"><code v-html="highlightXml(xml)"></code></pre>
  </details>
</template>

<script setup>
import { ref, watch } from 'vue'
import { api } from '../api'

const props = defineProps({
  nodeId:      { type: String, required: true },
  hasChildren: { type: Boolean, default: false },
})

const xml          = ref(null)
const loading      = ref(false)
const error        = ref(null)
const withChildren = ref(false)

// Autre composant : l'XML affiché n'est plus le bon.
watch(() => props.nodeId, () => { xml.value = null; error.value = null; withChildren.value = false })

function onToggle(e) {
  if (e.target.open && xml.value === null) load()
}

async function load() {
  loading.value = true
  error.value = null
  try {
    xml.value = await api.getRaw(props.nodeId, withChildren.value)
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

function highlightXml(text) {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
    .replace(/(&lt;!--[\s\S]*?--&gt;)/g, '<span class="xml-comment">$1</span>')
    .replace(/(&lt;\/?)([\w:-]+)/g, '$1<span class="xml-tag">$2</span>')
    .replace(/([\w:-]+)(=)(&quot;[^&]*&quot;)/g, '<span class="xml-attr">$1</span>$2<span class="xml-val">$3</span>')
}
</script>

<style scoped>
.raw-ead {
  margin-top: 1.4rem;
  border-top: 1px solid var(--color-border);
  padding-top: .6rem;
}
.raw-ead summary {
  cursor: pointer;
  font-size: .8rem;
  color: var(--color-muted);
  user-select: none;
  list-style: none;
  display: inline-flex;
  align-items: center;
  gap: .4rem;
}
.raw-ead summary::-webkit-details-marker { display: none; }
.raw-ead summary::before {
  content: '▸';
  font-size: .7rem;
  transition: transform .15s;
}
.raw-ead[open] summary::before { transform: rotate(90deg); }
.raw-ead summary:hover { color: var(--color-primary); }
.raw-children { display: block; font-size: .78rem; color: var(--color-muted); margin-top: .4rem; }
.raw-loading { font-size: .82rem; color: var(--color-muted); padding: .5rem 0; font-style: italic; }
.raw-error   { font-size: .82rem; color: #c0392b; padding: .5rem 0; }
.raw-pre {
  margin-top: .6rem;
  padding: .8rem 1rem;
  background: #f8f7f4;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  font-family: ui-monospace, 'Cascadia Code', monospace;
  font-size: .75rem;
  line-height: 1.55;
  overflow-x: auto;
  white-space: pre;
  tab-size: 2;
}
/* Contenu injecté par v-html : hors de la portée des styles scoped sans :deep */
.raw-pre :deep(.xml-tag)     { color: #1a4a7a; font-weight: 600; }
.raw-pre :deep(.xml-attr)    { color: #7a4a1a; }
.raw-pre :deep(.xml-val)     { color: #2a7a2a; }
.raw-pre :deep(.xml-comment) { color: #888; font-style: italic; }
</style>
