<template>
  <main>Alerts</main>
</template>

<script setup lang="ts">
axios.get(`/api/alerts/${alertId}`)
request.post("/api/alerts/search", filters)
</script>
