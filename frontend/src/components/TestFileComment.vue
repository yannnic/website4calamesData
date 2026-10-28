<template>
  <!-- Corpus de test : ce que le fichier teste (commentaire en tête du fichier EAD). -->
  <template v-if="CORPUS === 'test' && comment">
    <p v-if="summary" class="test-comment-summary">{{ firstSentence }}</p>
    <div v-else class="test-comment">
      <div class="test-comment-label">Fichier de test</div>
      <pre>{{ comment }}</pre>
    </div>
  </template>
</template>

<script setup>
import { computed } from 'vue'
import { CORPUS } from '../api'

const props = defineProps({
  comment: { type: String, default: '' },
  summary: { type: Boolean, default: false },   // première phrase seulement
})

const firstSentence = computed(() => {
  const m = props.comment.match(/^[\s\S]*?\.(?=\s|$)/)
  return (m ? m[0] : props.comment).replace(/\s+/g, ' ')
})
</script>

<style scoped>
.test-comment {
  background: #fdf6ec; border: 1px solid #f0d9b0; border-radius: var(--radius);
  padding: .6rem .8rem; margin-bottom: 1.2rem;
}
.test-comment-label { font-size: .75rem; font-weight: bold; color: #8a5a14; text-transform: uppercase; letter-spacing: .04em; margin-bottom: .3rem; }
.test-comment pre { margin: 0; white-space: pre-wrap; font-size: .82rem; line-height: 1.45; color: var(--color-text); }
.test-comment-summary { font-size: .85rem; color: #8a5a14; margin: .2rem 0 0; }
</style>
