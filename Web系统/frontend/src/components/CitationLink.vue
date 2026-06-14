<script setup lang="ts">
defineProps<{
  nodeId: string
  marker: string
}>()

const emit = defineEmits<{
  'click': [nodeId: string]
}>()
</script>

<template>
  <span class="citation-link" @click="emit('click', nodeId)" :title="nodeId">
    【{{ marker }}】
  </span>
</template>

<style scoped>
.citation-link {
  display: inline;
  color: var(--accent);
  cursor: pointer;
  font-weight: 500;
  font-size: 0.9em;
  transition: background 0.15s;
  padding: 0 1px;
}

.citation-link:hover {
  background: #B5503C1A;
  border-radius: 2px;
}
</style>
