<template>
  <span class="cd" :title="label">
    <svg width="11" height="12" viewBox="0 0 11 12" fill="none">
      <line
        v-for="i in 4" :key="i"
        x1="0" :y1="(4 - i) * 3 + 1.5"
        x2="11" :y2="(4 - i) * 3 + 1.5"
        stroke="currentColor"
        stroke-width="1.4"
        stroke-linecap="round"
        :opacity="i <= tier ? 0.75 : 0.13"
      />
    </svg>
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ count: { type: Number, default: 0 } })

const tier = computed(() => {
  if (props.count === 0)  return 0
  if (props.count <= 5)   return 1
  if (props.count <= 30)  return 2
  if (props.count <= 150) return 3
  return 4
})

const label = computed(() =>
  props.count === 0 ? 'Aucun sous-élément'
    : `${props.count} sous-élément${props.count > 1 ? 's' : ''}`
)
</script>

<style scoped>
.cd {
  display: inline-flex;
  align-items: center;
  color: var(--color-muted);
  vertical-align: middle;
  flex-shrink: 0;
}
</style>
