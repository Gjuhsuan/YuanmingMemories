<script setup lang="ts">
import { nodeColors } from '@/theme/palette'

const props = defineProps<{
  counts?: Record<string, number>
}>()

const labels: Record<string, string> = {
  Event: '事件', Person: '人物', Place: '地点', Organization: '机构',
  Object: '客体', Document: '文献', AbstractNorm: '抽象规范', TemporalInterval: '时间区间',
}
</script>

<template>
  <div class="legend-list">
    <div
      v-for="(color, label) in nodeColors"
      :key="label"
      class="legend-item"
      :class="{ primary: label === 'Event' }"
    >
      <span class="legend-dot" :style="{ background: color }"></span>
      <span class="legend-name">{{ labels[label] }}</span>
      <span v-if="counts?.[label]" class="legend-n">{{ counts[label] }}</span>
      <span v-if="label === 'Event'" class="focus-mark">★</span>
    </div>
  </div>
</template>

<style scoped>
.legend-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  padding: 2px 0;
}

.legend-item.primary {
  font-weight: 500;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-name {
  color: var(--text-primary);
  flex: 1;
}

.legend-n {
  font-size: 11px;
  color: var(--text-muted);
  font-family: "Roboto Mono", monospace;
}

.focus-mark {
  font-size: 10px;
  color: var(--accent);
}
</style>
