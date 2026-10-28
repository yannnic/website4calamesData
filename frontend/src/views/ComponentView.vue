<template>
  <div class="component-page">
    <p v-if="loading" class="loading container" style="padding-top:2rem">Chargement…</p>
    <p v-else-if="error" class="error container">{{ error }}</p>
    <template v-else-if="comp">

      <!-- ══ Retour ══ -->
      <div v-if="canGoBack" class="back-row container">
        <a class="back-link" href="#" @click.prevent="router.back()">← Retour aux résultats</a>
      </div>

      <!-- ══ Escalier + bouton arbre ══ -->
      <div class="staircase-row container">
        <div class="staircase-left-col">
          <button
            class="tree-toggle-btn"
            :class="{ active: showTree }"
            @click="showTree = !showTree"
            :title="showTree ? 'Masquer l\'arborescence' : 'Afficher l\'arborescence'"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round">
              <line x1="7" y1="1" x2="7" y2="5"/>
              <circle cx="7" cy="1" r="1" fill="currentColor" stroke="none"/>
              <line x1="7" y1="5" x2="3" y2="9"/>
              <line x1="7" y1="5" x2="11" y2="9"/>
              <circle cx="3"  cy="10" r="1.3" fill="currentColor" stroke="none"/>
              <circle cx="11" cy="10" r="1.3" fill="currentColor" stroke="none"/>
              <circle cx="7"  cy="10" r="1.3" fill="currentColor" stroke="none"/>
              <line x1="7" y1="5" x2="7" y2="9"/>
            </svg>
          </button>
        </div>
      <nav class="staircase">
        <div class="stair stair--home" :style="{ '--step': 0 }">
          <RouterLink to="/" class="stair-link">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg>
            Accueil
          </RouterLink>
        </div>
        <div v-for="(anc, i) in ancestors" :key="anc.node_id" class="stair" :style="{ '--step': i + 1 }">
          <RouterLink :to="ancLink(anc)" class="stair-link">
            <span v-if="levelLabel(anc.level)" class="level-badge" :class="`level-${anc.level}`" style="font-size:.58rem">{{ levelLabel(anc.level) }}</span>
            {{ anc.title }}
          </RouterLink>
        </div>
      </nav>
      </div><!-- fin staircase-row -->

      <!-- ══ Indicateur de position ══ -->
      <div v-if="siblings.length > 1" class="sibling-indicator container">

        <!-- Barre de navigation -->
        <div class="sib-track">
          <template v-if="siblings.length <= 20">
            <span
              v-for="(sib, i) in siblings" :key="sib.node_id"
              class="sibling-dot"
              :class="{ 'sibling-dot--current': i === siblingIndex }"
              @mouseenter="hoverIndex = i"
              @mouseleave="hoverIndex = null"
              @click="i !== siblingIndex && goTo(sib)"
            />
          </template>
          <template v-else>
            <button class="sib-nav" :disabled="!prevSibling" @click="prevSibling && goTo(prevSibling)">←</button>
            <input
              type="range"
              class="sib-range"
              :min="0"
              :max="siblings.length - 1"
              :value="siblingIndex"
              @input="onSliderInput"
              @change="onSliderChange"
              @mousemove="onSliderMouseMove"
              @mouseleave="hoverIndex = null"
            />
            <button class="sib-nav" :disabled="!nextSibling" @click="nextSibling && goTo(nextSibling)">→</button>
          </template>
        </div>

        <!-- Titre et position -->
        <div class="sib-info">
          <span class="sib-bubble" :class="{ 'sib-bubble--hover': activeIdx !== null }">
            <span class="sib-bubble-pos">{{ (activeIdx ?? siblingIndex) + 1 }}&thinsp;/&thinsp;{{ siblings.length }}</span>
            <transition name="sib-fade">
              <span v-if="activeIdx !== null" class="sib-bubble-title">{{ siblings[activeIdx]?.title }}</span>
            </transition>
          </span>
        </div>

      </div>

      <!-- ══ Frères + composant ══ -->
      <div class="sibling-stage container" :class="{ 'sibling-stage--tree': showTree }">

        <!-- Colonne gauche : arbre ou frère gauche -->
        <div class="left-col">

          <!-- Panneau arborescence -->
          <div v-if="showTree" class="tree-panel">
            <button class="tree-close" @click="showTree = false" title="Fermer">×</button>
            <TreeNode
              v-if="ancestors.length"
              :node-id="ancestors[0].node_id"
              :title="ancestors[0].title"
              :level="ancestors[0].level"
              :depth="0"
              :ead-id="ancestors[0].ead_id"
              :children-count="ancestors[0].children_count ?? 1"
              :expanded-path="expandedPath"
              :current-node-id="comp.node_id"
            />
            <TreeNode
              v-else
              :node-id="comp.node_id"
              :title="comp.title"
              :level="comp.level"
              :depth="0"
              :ead-id="comp.ead_id"
              :children-count="children.length"
              :expanded-path="expandedPath"
              :current-node-id="comp.node_id"
            />
          </div>

          <!-- Frère gauche (si arbre masqué) -->
          <template v-else>
            <div v-if="prevSibling" class="sibling-peek sibling-peek--left" @click="goTo(prevSibling)" :title="prevSibling.title">
              <div class="peek-arrow">← <span class="peek-count">{{ siblingIndex }}</span></div>
              <div class="peek-content">
                <div style="display:flex;align-items:center;gap:.4rem">
                  <span v-if="levelLabel(prevSibling.level)" class="level-badge" :class="`level-${prevSibling.level}`" style="font-size:.58rem">{{ levelLabel(prevSibling.level) }}</span>
                  <ChildrenDensity :count="prevSibling.children_count ?? 0" />
                </div>
                <span class="peek-title">{{ prevSibling.title }}</span>
                <span v-if="prevSibling.date_display" class="peek-date">{{ prevSibling.date_display }}</span>
              </div>
            </div>
            <div v-else class="sibling-peek sibling-peek--empty" />
          </template>

        </div><!-- fin left-col -->

        <div class="component-card">

        <h1 style="text-align:center">
          <span v-if="levelLabel(comp.level)" class="level-badge" :class="`level-${comp.level}`" style="font-size:.8rem">{{ levelLabel(comp.level) }}</span>
          <ChildrenDensity :count="children.length" style="margin:0 .4rem" />
          {{ comp.title }}
        </h1>
        <div class="meta" style="margin:.35rem 0 1rem;font-size:.9rem;color:var(--color-muted);text-align:center">
          <span v-if="comp.unitid">{{ comp.unitid }}</span>
          <span v-if="comp.unitid && comp.date_display"> &nbsp;·&nbsp; </span>
          <span v-if="comp.date_display">{{ comp.date_display }}</span>
        </div>
        <!-- Racine d'un fichier rattaché (liaisons) : sa description de test -->
        <TestFileComment :comment="comp.file_comment" />

        <!-- Description -->
        <div v-if="comp.abstract || comp.scope_content || comp.biography" class="description-block">
          <p v-if="comp.abstract">{{ comp.abstract }}</p>
          <p v-if="comp.scope_content" :class="comp.abstract ? 'scope-extra' : ''">{{ comp.scope_content }}</p>
          <p v-if="comp.biography" style="font-style:italic">{{ comp.biography }}</p>
        </div>

        <!-- Métadonnées -->
        <dl class="meta-grid" v-if="comp.extents?.length || comp.phys_facets?.length || comp.languages?.length || comp.access_restrict || comp.use_restrict">
          <template v-if="comp.extents?.length"><dt>Importance</dt><dd>{{ comp.extents.join(' — ') }}</dd></template>
          <template v-if="comp.phys_facets?.length"><dt>Support</dt><dd>{{ comp.phys_facets.join(' — ') }}</dd></template>
          <template v-if="comp.languages?.length"><dt>Langues</dt><dd>{{ comp.languages.join(', ') }}</dd></template>
          <template v-if="comp.access_restrict"><dt>Accès</dt><dd>{{ comp.access_restrict }}</dd></template>
          <template v-if="comp.use_restrict"><dt>Utilisation</dt><dd>{{ comp.use_restrict }}</dd></template>
        </dl>

        <!-- Termes d'indexation -->
        <dl v-if="hasIndexTerms" class="index-terms">
          <template v-if="comp.subjects?.length">
            <dt>Sujets</dt>
            <dd class="tag-list">
              <RouterLink v-for="s in comp.subjects" :key="s" :to="{ path: '/search', query: { subject: s } }" class="tag">{{ s }}</RouterLink>
            </dd>
          </template>
          <template v-if="comp.pers_names?.length">
            <dt>Personnes</dt>
            <dd class="tag-list">
              <RouterLink v-for="s in comp.pers_names" :key="s" :to="{ path: '/search', query: { pers_name: s } }" class="tag">{{ s }}</RouterLink>
            </dd>
          </template>
          <template v-if="comp.corp_names?.length">
            <dt>Collectivités</dt>
            <dd class="tag-list">
              <RouterLink v-for="s in comp.corp_names" :key="s" :to="{ path: '/search', query: { corp_name: s } }" class="tag">{{ s }}</RouterLink>
            </dd>
          </template>
          <template v-if="comp.fam_names?.length">
            <dt>Familles</dt>
            <dd class="tag-list">
              <RouterLink v-for="s in comp.fam_names" :key="s" :to="{ path: '/search', query: { q: s } }" class="tag">{{ s }}</RouterLink>
            </dd>
          </template>
          <template v-if="comp.geo_names?.length">
            <dt>Lieux</dt>
            <dd class="tag-list">
              <RouterLink v-for="s in comp.geo_names" :key="s" :to="{ path: '/search', query: { geo_name: s } }" class="tag">{{ s }}</RouterLink>
            </dd>
          </template>
          <template v-if="comp.genre_forms?.length">
            <dt>Genre/forme</dt>
            <dd class="tag-list">
              <RouterLink v-for="s in comp.genre_forms" :key="s" :to="{ path: '/search', query: { genre_form: s } }" class="tag">{{ s }}</RouterLink>
            </dd>
          </template>
        </dl>

        <!-- Vue EAD brute -->
        <RawEad :node-id="comp.node_id" :has-children="children.length > 0" />

        <!-- Enfants -->
        <section v-if="children.length" style="margin-top:1.8rem">
          <h2 style="margin-bottom:.8rem">
            Contenu
            <span style="font-weight:normal;font-size:.85rem;color:var(--color-muted)">
              ({{ children.length }} éléments)
            </span>
          </h2>
          <ComponentTree
            v-for="child in children"
            :key="child.node_id"
            :node-id="child.node_id"
            :initial-title="child.title"
            :initial-date="child.date_display"
            :level="child.level"
            :depth="child.depth"
            :ead-id="child.ead_id"
            :initial-children-count="child.children_count ?? 0"
          />
        </section>

        </div><!-- fin component-card -->

        <!-- Frère droit -->
        <div v-if="nextSibling" class="sibling-peek sibling-peek--right" @click="goTo(nextSibling)" :title="nextSibling.title">
          <div class="peek-arrow"><span class="peek-count">{{ siblings.length - siblingIndex - 1 }}</span> →</div>
          <div class="peek-content">
            <div style="display:flex;align-items:center;gap:.4rem">
              <span v-if="levelLabel(nextSibling.level)" class="level-badge" :class="`level-${nextSibling.level}`" style="font-size:.58rem">{{ levelLabel(nextSibling.level) }}</span>
              <ChildrenDensity :count="nextSibling.children_count ?? 0" />
            </div>
            <span class="peek-title">{{ nextSibling.title }}</span>
            <span v-if="nextSibling.date_display" class="peek-date">{{ nextSibling.date_display }}</span>
          </div>
        </div>
        <div v-else class="sibling-peek sibling-peek--empty" />

      </div><!-- fin sibling-stage -->

    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { componentPath as cPath, encodeNodeId, decodeNodeId } from '../router'
import { api } from '../api'
import { levelLabel } from '../utils/levels'
import ComponentTree from '../components/ComponentTree.vue'
import ChildrenDensity from '../components/ChildrenDensity.vue'
import TreeNode from '../components/TreeNode.vue'
import TestFileComment from '../components/TestFileComment.vue'
import RawEad from '../components/RawEad.vue'

const route  = useRoute()
const router = useRouter()

const comp      = ref(null)
const ancestors = ref([])
const siblings  = ref([])
const children  = ref([])
const loading   = ref(true)
const error     = ref(null)

const siblingIndex = computed(() =>
  siblings.value.findIndex(s => s.node_id === comp.value?.node_id)
)

const canGoBack = window.history.length > 1

const hasIndexTerms = computed(() =>
  comp.value && (
    comp.value.subjects?.length ||
    comp.value.pers_names?.length ||
    comp.value.corp_names?.length ||
    comp.value.fam_names?.length ||
    comp.value.geo_names?.length ||
    comp.value.genre_forms?.length
  )
)
const prevSibling = computed(() =>
  siblingIndex.value > 0 ? siblings.value[siblingIndex.value - 1] : null
)
const nextSibling = computed(() =>
  siblingIndex.value >= 0 && siblingIndex.value < siblings.value.length - 1
    ? siblings.value[siblingIndex.value + 1] : null
)

async function load(param) {
  const nodeId = decodeNodeId(param)
  loading.value = true
  error.value = null
  siblings.value = []
  children.value = []
  try {
    ;[comp.value, ancestors.value] = await Promise.all([
      api.getComponent(nodeId),
      api.getAncestors(nodeId),
    ])
    const [sibs, kids] = await Promise.all([
      comp.value.parent_id ? api.getChildren(comp.value.parent_id) : Promise.resolve([]),
      api.getChildren(nodeId),
    ])
    siblings.value = sibs
    children.value = kids
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// ── Arborescence ──
const showTree     = ref(false)
const expandedPath = computed(() => new Set(ancestors.value.map(a => a.node_id)))

function ancLink(anc) {
  if (anc.depth === 0) return { name: 'fonds', params: { eadId: anc.ead_id } }
  return cPath(anc.node_id)
}

function goTo(sib) {
  router.push(cPath(sib.node_id))
}

// ── Slider frères ──
const dragIndex  = ref(null)
const hoverIndex = ref(null)
const activeIdx  = computed(() => dragIndex.value ?? hoverIndex.value)

function onSliderInput(e) {
  dragIndex.value = parseInt(e.target.value)
}

function onSliderChange(e) {
  const idx = parseInt(e.target.value)
  dragIndex.value = null
  if (!isNaN(idx) && idx !== siblingIndex.value) goTo(siblings.value[idx])
}

function onSliderMouseMove(e) {
  const rect = e.currentTarget.getBoundingClientRect()
  const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
  hoverIndex.value = Math.round(ratio * (siblings.value.length - 1))
}

onMounted(() => load(route.params.nodeId))
watch(() => route.params.nodeId, (id) => { if (id) load(id) })
</script>

<style scoped>
.component-page {
  padding-bottom: 3rem;
  min-height: 100vh;
}

/* ── Indicateur position ── */
.sibling-indicator {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: .3rem;
  padding: .5rem 0 .2rem;
}
.sib-track {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: .35rem;
  width: 100%;
}
.sib-info {
  display: flex;
  justify-content: center;
  min-height: 1.8em;
  margin-top: .15rem;
}
.sib-bubble {
  display: inline-flex;
  align-items: baseline;
  gap: .5rem;
  padding: .2rem .75rem;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  color: var(--color-muted);
  border-radius: 99px;
  font-size: .78rem;
  max-width: 480px;
  overflow: hidden;
  transition: background .15s, border-color .15s, color .15s;
}
.sib-bubble--hover {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
}
.sib-bubble-pos {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  flex-shrink: 0;
}
.sib-bubble-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: .9;
}
.sib-fade-enter-active, .sib-fade-leave-active { transition: opacity .12s; }
.sib-fade-enter-from, .sib-fade-leave-to { opacity: 0; }

/* Points (≤ 20 frères) */
.sibling-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--color-border);
  cursor: pointer;
  transition: background .3s, transform .3s;
  flex-shrink: 0;
}
.sibling-dot:hover { background: var(--color-muted); }
.sibling-dot--current { background: var(--color-accent); transform: scale(1.4); cursor: default; }

/* Barre (> 20 frères) */
.sib-nav {
  background: none; border: 1px solid var(--color-border);
  border-radius: var(--radius); padding: 1px 8px;
  cursor: pointer; font-size: .85rem; color: var(--color-muted);
  transition: color .3s, border-color .3s;
}
.sib-nav:hover:not(:disabled) { color: var(--color-accent); border-color: var(--color-accent); }
.sib-nav:disabled { opacity: .3; cursor: default; }

.sib-range {
  flex: 1;
  max-width: 400px;
  accent-color: var(--color-primary);
  cursor: pointer;
}

/* ── Colonne gauche ── */
.left-col {
  flex: 0 0 180px;
  align-self: stretch;
  position: sticky;
  top: 4.5rem;
  transition: flex-basis .3s;
  display: flex;
  flex-direction: column;
}

/* ── Panneau arborescence ── */
.tree-close {
  display: block;
  margin: .3rem .3rem .3rem auto;
  background: none;
  border: none;
  font-size: 1.1rem;
  line-height: 1;
  color: var(--color-muted);
  cursor: pointer;
  padding: .1rem .4rem;
  border-radius: var(--radius);
}
.tree-close:hover { color: var(--color-text); background: var(--color-surface-alt, #f0f0f0); }

.tree-panel {
  position: fixed;
  left: 0;
  top: 4.5rem;
  bottom: 0;
  /* right = marge auto du container + padding container + left-col + gap */
  right: calc(max(0px, (100vw - 1100px) / 2) + 1.5rem + 180px + .6rem);
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: thin;
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  padding: .4rem 0;
  z-index: 50;
}

/* ── Frères + centre ── */
.sibling-stage {
  display: flex;
  align-items: flex-start;
  gap: .6rem;
  position: relative;
}

.sibling-peek {
  flex: 0 0 180px;
  min-height: 0;
  cursor: pointer;
  opacity: .5;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  display: flex;
  flex-direction: row;
  align-items: stretch;
  overflow: hidden;
  transition: opacity .4s, box-shadow .4s;
  margin-top: .8rem;
}
/* Gauche : flèche sur le bord droit (côté carte) */
.sibling-peek--left {
  flex-direction: row-reverse;
  mask-image: linear-gradient(to right, transparent 0%, black 40%);
}
/* Droite : flèche sur le bord gauche (côté carte) */
.sibling-peek--right {
  mask-image: linear-gradient(to left, transparent 0%, black 40%);
}
.sibling-peek:hover {
  opacity: .9;
  box-shadow: var(--shadow-md);
}
.sibling-peek--empty { opacity: 0; pointer-events: none; }

.peek-arrow {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: .25rem;
  padding: .6rem .5rem;
  font-size: 1.1rem;
  color: var(--color-accent);
}
.sibling-peek--left .peek-arrow {
  border-left: 1px solid var(--color-border);
  border-right: none;
}
.sibling-peek--right .peek-arrow {
  border-left: none;
  border-right: 1px solid var(--color-border);
}
.peek-count { font-size: .68rem; font-variant-numeric: tabular-nums; color: var(--color-muted); }
.peek-content { flex: 1; min-width: 0; padding: .6rem .7rem; display: flex; flex-direction: column; gap: .35rem; }
.peek-title { font-size: .75rem; font-weight: 600; line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 6; -webkit-box-orient: vertical; overflow: hidden; }
.peek-date { font-size: .68rem; color: var(--color-muted); }

.component-card {
  flex: 1;
  min-width: 0;
  border-radius: var(--radius);
  padding: 1.5rem;
  margin-top: .8rem;
  background: #fffdf7;
  border: 1px solid #e2dcd0;
  box-shadow:
    0 2px 8px rgba(0,0,0,.06),
    0 8px 28px rgba(0,0,0,.08);
}


.back-row {
  padding: .4rem 0 0;
}
.back-link {
  font-size: .82rem;
  color: var(--color-muted);
  text-decoration: none;
}
.back-link:hover {
  color: var(--color-primary);
  text-decoration: underline;
}

/* ── Escalier d'ancêtres ── */
.staircase-row {
  display: flex;
  align-items: flex-start;
  gap: .6rem;
  padding-top: .8rem;
}
.staircase-left-col {
  flex: 0 0 180px;
  display: flex;
  justify-content: flex-end;
  padding-right: .2rem;
}
.tree-toggle-btn {
  flex-shrink: 0;
  width: 26px; height: 26px;
  display: flex; align-items: center; justify-content: center;
  background: none;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  cursor: pointer;
  color: var(--color-muted);
  transition: color .3s, border-color .3s, background .3s;
  margin-top: .1rem;
}
.tree-toggle-btn:hover,
.tree-toggle-btn.active {
  color: var(--color-primary);
  border-color: var(--color-primary);
  background: rgba(26,74,122,.06);
}
.staircase {
  flex: 1;
  padding-bottom: .4rem;
}

.stair {
  display: flex;
  align-items: center;
  margin-left: calc(1.5rem + var(--step) * 1.6rem);
  margin-bottom: .15rem;
  position: relative;
}

/* Crochet horizontal */
.stair::after {
  content: '';
  position: absolute;
  left: -1rem;
  top: 50%;
  width: .8rem;
  height: 1px;
  background: var(--color-border);
}
.stair--home::after { display: none; }

.stair-link {
  display: inline-flex;
  align-items: center;
  gap: .35rem;
  font-size: .82rem;
  color: var(--color-muted);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: .2rem .65rem;
  white-space: nowrap;
  max-width: min(28rem, 60vw);
  overflow: hidden;
  text-overflow: ellipsis;
  transition: border-color .4s, color .4s, background .4s;
}
.stair-link:hover {
  color: #c8911c;
  border-color: var(--color-primary);
  background: var(--color-bg);
  text-decoration: none;
}

.stair--home .stair-link { color: var(--color-muted); }


/* ── Carrousel ── */
.carousel-section {
  position: relative;
  background: linear-gradient(180deg, var(--color-surface) 0%, var(--color-bg) 100%);
  border-bottom: 1px solid var(--color-border);
  padding: 1.2rem 0 .8rem;
  overflow: hidden;
}

.carousel-track {
  display: flex;
  gap: .8rem;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  scrollbar-width: none;
  padding: .4rem 3rem 1rem;
}
.carousel-track::-webkit-scrollbar { display: none; }

.carousel-card {
  flex-shrink: 0;
  scroll-snap-align: center;
  width: 200px;
  padding: .7rem .9rem;
  border-radius: var(--radius);
  border: 1px solid var(--color-border);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: .3rem;
  transition: all .25s ease;

  /* Par défaut : très atténué */
  background: var(--color-surface);
  opacity: .35;
  transform: scale(.9);
  box-shadow: none;
}

.carousel-card.is-far {
  opacity: .35;
  transform: scale(.9);
}

.carousel-card.is-adjacent {
  opacity: .7;
  transform: scale(.96);
  box-shadow: 0 2px 8px rgba(0,0,0,.1);
}

.carousel-card.is-current {
  opacity: 1;
  transform: scale(1.04);
  background: var(--color-surface);
  border-color: var(--color-primary);
  box-shadow: 0 4px 20px rgba(26,74,122,.2), 0 1px 4px rgba(0,0,0,.1);
  cursor: default;
}

.carousel-card:not(.is-current):hover {
  opacity: .85;
  transform: scale(.98);
  box-shadow: 0 2px 10px rgba(0,0,0,.12);
}

.carousel-card-title {
  font-size: .82rem;
  font-weight: bold;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.carousel-card-date {
  font-size: .72rem;
  color: var(--color-muted);
  margin-top: auto;
}

/* Fondu sur les bords */
.carousel-fade {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 5rem;
  pointer-events: none;
  z-index: 2;
}
.carousel-fade--left {
  left: 0;
  background: linear-gradient(to right, var(--color-surface), transparent);
}
.carousel-fade--right {
  right: 0;
  background: linear-gradient(to left, var(--color-bg), transparent);
}

.carousel-pos {
  text-align: center;
  font-size: .75rem;
  color: var(--color-muted);
  margin-top: .2rem;
}

.description-block {
  background: var(--color-surface);
  border-left: 3px solid var(--color-accent);
  border-radius: 0 var(--radius) var(--radius) 0;
  padding: .9rem 1.1rem;
  margin: 1rem 0;
  font-size: .95rem;
  line-height: 1.7;
}
.description-block .scope-extra { margin-top: .6rem; color: var(--color-muted); }

.meta-grid {
  display: grid;
  grid-template-columns: 9rem 1fr;
  gap: .3rem .8rem;
  font-size: .88rem;
  margin-top: .8rem;
  padding: .5rem 0;
}
.meta-grid dt { color: var(--color-muted); font-style: italic; }

.index-terms {
  display: grid;
  grid-template-columns: 8rem 1fr;
  gap: .4rem .8rem;
  font-size: .85rem;
  margin-top: .9rem;
  padding-top: .7rem;
  border-top: 1px solid var(--color-border);
  align-items: start;
}
.index-terms dt {
  color: var(--color-muted);
  font-style: italic;
  padding-top: .15rem;
}
.index-terms dd .tag-list { margin-top: 0; }

/* Tags dans la carte : fond transparent, bordure fine */
.component-card .tag {
  background: transparent;
  border-color: var(--color-border);
  color: var(--color-muted);
  transition: border-color .4s, color .4s;
}
.component-card .tag:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}
</style>
