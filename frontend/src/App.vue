<template>
  <header class="site-header">
    <div class="container header-inner">
      <RouterLink to="/" class="logo">Calames</RouterLink>
      <form class="header-search" @submit.prevent="goSearch">
        <input v-model="q" type="text" placeholder="Rechercher dans les archives…" />
        <button type="submit" aria-label="Rechercher">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
        </button>
      </form>
      <nav>
        <RouterLink to="/">Accueil</RouterLink>
        <RouterLink :to="lastSearchUrl">Recherche</RouterLink>
        <RouterLink to="/search/advanced">Recherche avancée</RouterLink>
        <RouterLink to="/persons">Index des personnes</RouterLink>
        <RouterLink to="/depot">Déposer</RouterLink>
      </nav>
    </div>
  </header>

  <main>
    <RouterView v-slot="{ Component }">
      <keep-alive include="HomeView">
        <component :is="Component" />
      </keep-alive>
    </RouterView>
  </main>

  <footer class="site-footer">
    Calames HTML — catalogue des archives et manuscrits des bibliothèques de l'enseignement supérieur
  </footer>
</template>

<script setup>
import { ref, computed } from 'vue'
import { RouterLink, RouterView, useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route  = useRoute()
const q = ref('')

const SEARCH_PATHS = ['/search', '/search/advanced']

// Mémoriser la dernière URL de recherche
const lastSearchUrl = computed(() => {
  if (SEARCH_PATHS.some(p => route.path.startsWith(p))) {
    sessionStorage.setItem('lastSearchUrl', route.fullPath)
  }
  return sessionStorage.getItem('lastSearchUrl') || '/search'
})

function goSearch() {
  if (q.value.trim()) {
    router.push({ path: '/search', query: { q: q.value.trim() } })
    q.value = ''
  }
}
</script>
