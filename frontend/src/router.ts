import { createRouter, createWebHistory } from "vue-router"

import GraphView from "@/views/GraphView.vue"
import ProjectView from "@/views/ProjectView.vue"
import SearchView from "@/views/SearchView.vue"

export const routes = [
  { path: "/", redirect: "/projects" },
  { path: "/projects", component: ProjectView },
  { path: "/search", component: SearchView },
  { path: "/graph", component: GraphView },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
