<template>
  <details :open="startOpen || depth === 0" class="tree-node" @toggle="onToggle">
    <summary>
      <span class="level-badge" :class="`level-${level || 'fonds'}`" style="font-size:.65rem">{{ levelLabel }}</span>
      <ChildrenDensity :count="childCount ?? 0" style="margin-right:.3rem;opacity:.7" />
      <RouterLink :to="nodeLink" class="node-title" @click.stop>{{ initialTitle }}</RouterLink>
      <span v-if="initialDate" class="node-date">{{ initialDate }}</span>
    </summary>

    <div v-if="open">
      <p v-if="loadingChildren" class="loading" style="padding:.3rem .8rem;font-size:.82rem">Chargement…</p>
      <p v-else-if="childError" class="error" style="font-size:.82rem">{{ childError }}</p>
      <ComponentTree
        v-for="child in children"
        :key="child.node_id"
        :node-id="child.node_id"
        :initial-title="child.title"
        :initial-date="child.date_display"
        :level="child.level"
        :depth="child.depth"
        :ead-id="child.ead_id"
      />
    </div>
  </details>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { levelLabel as ll } from '../utils/levels'
import ChildrenDensity from './ChildrenDensity.vue'
import { RouterLink } from 'vue-router'
import { componentPath as cPath } from '../router'
import { api } from '../api'

const props = defineProps({
  nodeId:       { type: String, required: true },
  initialTitle: { type: String, default: '' },
  initialDate:  { type: String, default: '' },
  level:        { type: String, default: '' },
  depth:        { type: Number, default: 0 },
  eadId:        { type: String, default: '' },
  startOpen:           { type: Boolean, default: false },
  initialChildrenCount:{ type: Number,  default: null },
})

const children        = ref([])
const loadingChildren = ref(false)
const childError      = ref(null)
const open            = ref(props.startOpen || props.depth === 0)
const childCount      = ref(props.initialChildrenCount)

const levelLabel = computed(() => ll(props.level || 'fonds'))
const nodeLink   = computed(() => {
  if (props.depth === 0) return { name: 'fonds', params: { eadId: props.eadId || props.nodeId.split('#')[0] } }
  return cPath(props.nodeId)
})

function onToggle(e) {
  open.value = e.target.open
}

async function loadChildren() {
  if (children.value.length) return
  loadingChildren.value = true
  childError.value = null
  try {
    children.value = await api.getChildren(props.nodeId)
    childCount.value = children.value.length
  } catch (e) {
    childError.value = e.message
  } finally {
    loadingChildren.value = false
  }
}

watch(open, (val) => { if (val) loadChildren() }, { immediate: true })
</script>
