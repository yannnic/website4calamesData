<template>
  <!-- Adresses de Calames : https://calames.abes.fr/pub/ms/<id> (FileId-<N> ou @id
       d'un composant) et l'ancienne forme /pub/#details?id=<id>. Redirige vers la
       page correspondante, pour que les liens existants continuent de fonctionner. -->
  <div class="container">
    <p v-if="error" class="error">{{ error }}</p>
    <p v-else class="loading">Redirection…</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { componentPath } from '../router'

const route = useRoute()
const router = useRouter()
const error = ref(null)

function calamesId() {
  if (route.params.id) return String(route.params.id)
  const m = route.hash.match(/[?&]id=([^&]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}

onMounted(async () => {
  const id = calamesId()
  if (!id) { router.replace('/'); return }
  try {
    const hit = await api.resolve(id)
    router.replace(hit.depth === 0
      ? { name: 'fonds', params: { eadId: hit.ead_id } }
      : componentPath(hit.node_id))
  } catch {
    error.value = `Notice Calames introuvable : ${id}`
  }
})
</script>
