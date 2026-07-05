<script setup lang="ts">
import { RouterLink } from "vue-router"
</script>

<template>
  <nav class="app-nav" data-test="app-nav" aria-label="Primary navigation">
    <RouterLink class="brand" to="/projects">ResearchCode-Agent</RouterLink>
    <div class="links">
      <RouterLink to="/projects">Projects</RouterLink>
      <RouterLink to="/search">Search</RouterLink>
      <RouterLink to="/graph">Graph</RouterLink>
    </div>
  </nav>
</template>

<style scoped>
.app-nav {
  position: sticky;
  z-index: 10;
  top: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 14px max(24px, calc((100vw - 1480px) / 2 + 32px));
  border-bottom: 1px solid rgba(203, 213, 225, 0.8);
  background: rgba(248, 250, 252, 0.9);
  backdrop-filter: blur(12px);
}

a {
  color: #475569;
  font-size: 0.9rem;
  font-weight: 700;
  text-decoration: none;
}

.brand {
  color: #0f172a;
  font-weight: 850;
}

.links {
  display: flex;
  gap: 8px;
}

.links a {
  padding: 8px 12px;
  border-radius: 9px;
}

.links a.router-link-active {
  background: #ccfbf1;
  color: #115e59;
}

@media (max-width: 560px) {
  .app-nav {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }
}
</style>
