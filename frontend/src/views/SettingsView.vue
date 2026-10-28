<template>
  <div class="container">
    <h1 style="margin-bottom:.6rem">Paramètres</h1>

    <h2 class="settings-title">LLM (recherche en langage naturel, résumés)</h2>
    <p class="settings-subtitle">
      Toute API compatible OpenAI : OpenAI, Mistral, Ollama… Ces réglages restent dans ce
      navigateur et sont transmis à l'API de Calames avec chaque requête IA. Laissés vides,
      c'est la configuration du serveur qui s'applique, s'il en a une.
    </p>

    <form class="settings-form" @submit.prevent="save">
      <label>
        URL de base
        <input v-model="form.baseUrl" type="url" :placeholder="LLM_DEFAULTS.baseUrl" />
      </label>
      <label>
        Clé API
        <input v-model="form.apiKey" type="password" autocomplete="off"
               placeholder="facultative pour un serveur local (Ollama…)" />
      </label>
      <label>
        Modèle
        <input v-model="form.model" type="text" :placeholder="LLM_DEFAULTS.model" />
      </label>
      <div class="settings-actions">
        <button type="submit">Enregistrer</button>
        <button type="button" class="secondary" :disabled="checking" @click="check">
          {{ checking ? 'Test…' : 'Tester' }}
        </button>
        <button type="button" class="secondary" @click="clear">Effacer</button>
      </div>
    </form>

    <p v-if="message" class="settings-message" :class="{ error: !message.ok }">{{ message.text }}</p>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { api, loadLlmSettings, saveLlmSettings, LLM_DEFAULTS } from '../api'

const form     = reactive(loadLlmSettings())
const message  = ref(null)
const checking = ref(false)

function save() {
  saveLlmSettings({ ...form })
  message.value = { ok: true, text: 'Réglages enregistrés dans ce navigateur.' }
}

function clear() {
  Object.assign(form, { baseUrl: '', apiKey: '', model: '' })
  save()
  message.value = { ok: true, text: 'Réglages effacés : la configuration du serveur s\'applique.' }
}

async function check() {
  saveLlmSettings({ ...form })
  checking.value = true
  message.value = null
  try {
    const res = await api.checkLlm()
    const who = res.source === 'client' ? 'vos réglages' : 'configuration du serveur'
    message.value = res.ok
      ? { ok: true, text: `LLM opérationnel (${who} : ${res.model}, ${res.base_url}).` }
      : { ok: false, text: `Échec (${who}) : ${res.error}` }
  } catch (e) {
    message.value = { ok: false, text: e.message }
  } finally {
    checking.value = false
  }
}
</script>

<style scoped>
.settings-title { font-size: 1.2rem; margin: 1rem 0 .4rem; }
.settings-subtitle { color: var(--color-muted); margin-bottom: 1rem; max-width: 46rem; }

.settings-form {
  display: flex; flex-direction: column; gap: .9rem; max-width: 34rem;
  background: var(--color-surface); border: 1px solid var(--color-border);
  border-radius: var(--radius); padding: 1rem; box-shadow: var(--shadow);
}
.settings-form label { display: flex; flex-direction: column; gap: .3rem; font-size: .9rem; color: var(--color-muted); }
.settings-form input { padding: .4rem .5rem; border: 1px solid var(--color-border); border-radius: var(--radius); }
.settings-actions { display: flex; gap: .6rem; }
.settings-actions button {
  padding: .5rem 1.2rem; border: none; border-radius: var(--radius);
  background: var(--color-primary); color: #fff; cursor: pointer;
}
.settings-actions button:hover:not(:disabled) { background: var(--color-primary-hover); }
.settings-actions button.secondary { background: var(--color-surface); color: var(--color-primary); border: 1px solid var(--color-border); }
.settings-actions button:disabled { opacity: .6; cursor: default; }

.settings-message { margin-top: 1rem; color: #2e7d32; }
.settings-message.error { color: #c0392b; }
</style>
