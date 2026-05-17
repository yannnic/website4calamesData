<template>
  <div class="tn-wrap">
    <div
      class="tn-row"
      :class="{
        'tn-row--current': isCurrent,
        'tn-row--path':    isInPath && !isCurrent,
      }"
      :style="{ '--d': depth }"
    >
      <!-- Toggle expand -->
      <button class="tn-toggle" @click="toggle" v-if="childrenCount > 0">
        <svg v-if="loading" width="8" height="8" viewBox="0 0 8 8" class="tn-spin">
          <circle cx="4" cy="4" r="3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-dasharray="10 4"/>
        </svg>
        <svg v-else-if="expanded" width="8" height="8" viewBox="0 0 8 8" fill="currentColor">
          <path d="M1 2.5 L4 5.5 L7 2.5"/>
        </svg>
        <svg v-else width="8" height="8" viewBox="0 0 8 8" fill="currentColor">
          <path d="M2.5 1 L5.5 4 L2.5 7"/>
        </svg>
      </button>
      <span v-else class="tn-leaf" />

      <!-- Lien ou label courant -->
      <RouterLink v-if="!isCurrent" :to="nodePath" class="tn-link" :title="title">
        <span class="level-badge" :class="`level-${level}`" style="font-size:.5rem;padding:0 .3rem;line-height:1.4">{{ levelLabel(level) }}</span>
        <span class="tn-title">{{ title }}</span>
        <ChildrenDensity :count="childrenCount" style="margin-left:.2rem;opacity:.6" />
      </RouterLink>
      <span v-else class="tn-link tn-link--current" :title="title">
        <span class="level-badge" :class="`level-${level}`" style="font-size:.5rem;padding:0 .3rem;line-height:1.4">{{ levelLabel(level) }}</span>
        <span class="tn-title">{{ title }}</span>
      </span>
    </div>

    <!-- Enfants -->
    <div v-if="expanded && fetchedChildren.length" class="tn-children">
      <TreeNode
        v-for="child in fetchedChildren"
        :key="child.node_id"
        :node-id="child.node_id"
        :title="child.title"
        :level="child.level"
        :depth="depth + 1"
        :ead-id="child.ead_id"
        :children-count="child.children_count ?? 0"
        :expanded-path="expandedPath"
        :current-node-id="currentNodeId"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { levelLabel } from '../utils/levels'
import { RouterLink } from 'vue-router'
import { encodeNodeId } from '../router'
import { api } from '../api'
import ChildrenDensity from './ChildrenDensity.vue'

const props = defineProps({
  nodeId:       { type: String,  required: true },
  title:        { type: String,  default: '' },
  level:        { type: String,  default: '' },
  depth:        { type: Number,  default: 0 },
  eadId:        { type: String,  default: '' },
  childrenCount:{ type: Number,  default: 0 },
  expandedPath: { type: Set,     default: () => new Set() },
  currentNodeId:{ type: String,  default: '' },
})

const expanded       = ref(false)
const loading        = ref(false)
const fetchedChildren = ref([])

const isCurrent = computed(() => props.nodeId === props.currentNodeId)
const isInPath  = computed(() => props.expandedPath.has(props.nodeId))

const nodePath = computed(() =>
  props.depth === 0
    ? { name: 'fonds', params: { eadId: props.eadId } }
    : { name: 'component', params: { nodeId: encodeNodeId(props.nodeId) } }
)

async function fetchChildren() {
  if (fetchedChildren.value.length) return
  loading.value = true
  try {
    fetchedChildren.value = await api.getChildren(props.nodeId)
  } finally {
    loading.value = false
  }
}

async function toggle() {
  if (!expanded.value) await fetchChildren()
  expanded.value = !expanded.value
}

onMounted(async () => {
  if (isInPath.value || isCurrent.value) {
    await fetchChildren()
    expanded.value = true
  }
})
</script>

<style scoped>
.tn-wrap { display: flex; flex-direction: column; }

.tn-row {
  display: flex;
  align-items: center;
  gap: .3rem;
  padding: .22rem .4rem .22rem calc(.5rem + var(--d, 0) * 1rem);
  border-radius: 3px;
  min-height: 1.7rem;
  transition: background .2s;
}
.tn-row:hover { background: rgba(26,74,122,.05); }
.tn-row--path { background: rgba(26,74,122,.04); }
.tn-row--current { background: rgba(26,74,122,.10); }

.tn-toggle {
  flex-shrink: 0;
  width: 16px; height: 16px;
  display: flex; align-items: center; justify-content: center;
  background: none; border: none;
  cursor: pointer;
  color: var(--color-muted);
  padding: 0;
  border-radius: 2px;
  transition: color .2s;
}
.tn-toggle:hover { color: var(--color-primary); }
.tn-toggle svg path { fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }

.tn-leaf {
  flex-shrink: 0;
  width: 16px; height: 16px;
}

.tn-link {
  display: flex;
  align-items: center;
  gap: .3rem;
  min-width: 0;
  font-size: .78rem;
  color: var(--color-muted);
  line-height: 1.3;
  transition: color .2s;
  flex: 1;
}
.tn-link:hover { color: var(--color-primary); text-decoration: none; }
.tn-link--current {
  color: var(--color-primary);
  font-weight: 600;
  cursor: default;
}
.tn-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

@keyframes spin { to { transform: rotate(360deg); } }
.tn-spin { animation: spin .8s linear infinite; }
</style>
