<template>
  <!-- Description complémentaire d'un composant, sous les libellés de Calames :
       producteur, organisme responsable, anciennes cotes, rubriques EAD,
       versions numériques. -->
  <dl v-if="hasContent" class="extra-desc">
    <template v-if="showCreators && doc.creators?.length">
      <dt>Producteur du fonds ou collectionneur</dt>
      <dd>
        <div v-for="c in doc.creators" :key="c.name + c.role">
          {{ c.name }}<span v-if="c.role" class="extra-muted"> ({{ roleLabel(c.role) }})</span>
        </div>
      </dd>
    </template>

    <!-- En entier à la racine d'un fichier (fonds) ; replié ailleurs : il est le même
         pour tous les composants d'un fonds. -->
    <template v-if="info">
      <dt>Organisme responsable</dt>
      <dd>
        <details :open="doc.file_root" class="extra-org">
          <summary>{{ info.name }}</summary>
          <div v-for="line in info.address" :key="line" class="extra-muted extra-text">{{ line }}</div>
          <div v-if="info.phone" class="extra-muted">Téléphone : {{ info.phone }}</div>
          <div v-if="info.email"><a :href="`mailto:${info.email}`">{{ info.email }}</a></div>
          <div v-if="info.website"><a :href="info.website" target="_blank" rel="noopener">Site web de la bibliothèque</a></div>
        </details>
      </dd>
    </template>

    <template v-if="doc.former_unitids?.length">
      <dt>Ancienne cote</dt>
      <dd>{{ doc.former_unitids.join(' ; ') }}</dd>
    </template>

    <template v-for="(sec, i) in doc.sections ?? []" :key="i">
      <dt>{{ SECTION_LABELS[sec.tag] ?? sec.tag }}</dt>
      <dd class="extra-text">{{ sec.text }}</dd>
    </template>

    <template v-if="doc.dao?.length">
      <dt>Version(s) numérique(s)</dt>
      <dd>
        <div v-for="d in doc.dao" :key="d.href">
          <a :href="d.href" target="_blank" rel="noopener">{{ d.title || d.href }}</a>
        </div>
      </dd>
    </template>
  </dl>
</template>

<script setup>
import { computed } from 'vue'
import { SECTION_LABELS, roleLabel } from '../utils/labels'

const props = defineProps({
  doc:          { type: Object, required: true },
  showCreators: { type: Boolean, default: false },   // la page du fonds les affiche déjà
})

const info = computed(() => props.doc.repository_info)
const hasContent = computed(() => {
  const d = props.doc
  return !!(info.value || d.former_unitids?.length || d.sections?.length || d.dao?.length
            || (props.showCreators && d.creators?.length))
})
</script>

<style scoped>
.extra-desc { margin: 1rem 0; font-size: .9rem; }
.extra-desc dt { font-weight: bold; color: var(--color-primary); margin-top: .7rem; font-size: .85rem; }
.extra-desc dd { margin: .15rem 0 0; }
.extra-text { white-space: pre-line; }
.extra-muted { color: var(--color-muted); }
.extra-org summary { cursor: pointer; }
.extra-org:not([open]) summary { color: var(--color-muted); font-size: .85rem; }
</style>
