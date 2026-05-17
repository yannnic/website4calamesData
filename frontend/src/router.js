import { createRouter, createWebHistory } from 'vue-router'
import HomeView from './views/HomeView.vue'
import SearchView from './views/SearchView.vue'
import AdvancedSearchView from './views/AdvancedSearchView.vue'
import FondsView from './views/FondsView.vue'
import ComponentView from './views/ComponentView.vue'
import PersonView from './views/PersonView.vue'
import PersonsView from './views/PersonsView.vue'

// node_id contains '#' which breaks URL paths (%23 is treated as fragment by servers).
// We use '/' as separator in URLs; ead_ids never contain '/'.
export const encodeNodeId = (nodeId) => nodeId.replace('#', '/')
export const decodeNodeId = (param)  => param.replace('/', '#')
export const componentPath = (nodeId) => ({ path: '/c/' + encodeNodeId(nodeId) })

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/',               component: HomeView },
    { path: '/search',         component: SearchView },
    { path: '/search/advanced', component: AdvancedSearchView, name: 'advanced-search' },
    { path: '/fonds/:eadId',   component: FondsView,     name: 'fonds' },
    { path: '/c/:nodeId(.*)',  component: ComponentView, name: 'component' },
    { path: '/persons',              component: PersonsView, name: 'persons' },
    { path: '/person/idref/:id',    component: PersonView,  name: 'person-idref' },
    { path: '/person/:name(.*)',    component: PersonView,  name: 'person' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
