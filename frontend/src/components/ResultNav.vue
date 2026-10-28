<template>
  <!-- Navigation dans la dernière liste de résultats (comme Calames) :
       résultat précédent / retour aux résultats / résultat suivant. -->
  <nav v-if="index >= 0" class="result-nav">
    <RouterLink v-if="prev" :to="pathOf(prev)">← Résultat précédent</RouterLink>
    <span v-else class="result-nav-off">← Résultat précédent</span>
    <RouterLink :to="saved.url" title="Retour aux résultats">Résultat {{ index + 1 }} / {{ saved.items.length }}</RouterLink>
    <RouterLink v-if="next" :to="pathOf(next)">Résultat suivant →</RouterLink>
    <span v-else class="result-nav-off">Résultat suivant →</span>
  </nav>
</template>

<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { componentPath } from '../router'
import { loadResults } from '../utils/results'

const props = defineProps({ nodeId: { type: String, required: true } })

// Relu à chaque changement de composant (la liste est écrite par la recherche).
const saved = computed(() => (props.nodeId, loadResults()))
const index = computed(() => saved.value.items.findIndex(i => i.node_id === props.nodeId))
const prev  = computed(() => saved.value.items[index.value - 1])
const next  = computed(() => saved.value.items[index.value + 1])

function pathOf(item) {
  return item.depth === 0 ? { name: 'fonds', params: { eadId: item.ead_id } } : componentPath(item.node_id)
}
</script>

<style scoped>
.result-nav { display: flex; justify-content: space-between; gap: 1rem; font-size: .82rem; margin-bottom: .8rem; }
.result-nav-off { color: var(--color-border); }
</style>
