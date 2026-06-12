<script setup lang="ts">
import { computed } from 'vue'
import { nodeColors } from '@/theme/palette'

const props = defineProps<{
  types: string[]
  selected: string[]
  meta?: any
}>()

const emit = defineEmits<{
  'change': [selected: string[]]
  'preset': [name: string]
}>()

const allTypes = ['Event', 'Person', 'Place', 'Organization', 'Object', 'Document', 'AbstractNorm', 'TemporalInterval']

const typeLabels: Record<string, string> = {
  Event: '事件', Person: '人物', Place: '地点', Organization: '机构',
  Object: '客体', Document: '文献', AbstractNorm: '抽象规范', TemporalInterval: '时间区间',
}

const presets = [
  { name: '仅事件', types: ['Event'] },
  { name: '事件+人物', types: ['Event', 'Person'] },
  { name: '事件+地点', types: ['Event', 'Place'] },
  { name: '全部', types: allTypes },
]

function toggleType(label: string) {
  const updated = props.selected.includes(label)
    ? props.selected.filter((t) => t !== label)
    : [...props.selected, label]
  if (updated.length > 0) {
    emit('change', updated)
  }
}

function applyPreset(name: string) {
  emit('preset', name)
}
</script>

<template>
  <div class="type-filter">
    <div class="filter-header">节点类型</div>
    <div class="filter-chips">
      <label
        v-for="t in allTypes"
        :key="t"
        class="filter-chip"
        :class="{ checked: selected.includes(t) }"
      >
        <input
          type="checkbox"
          :checked="selected.includes(t)"
          @change="toggleType(t)"
        />
        <span class="chip-dot" :style="{ background: nodeColors[t] }"></span>
        <span class="chip-text">{{ typeLabels[t] }}</span>
      </label>
    </div>

    <div class="presets">
      <span class="preset-label">预设：</span>
      <button
        v-for="p in presets"
        :key="p.name"
        class="preset-btn"
        @click="applyPreset(p.name)"
      >
        {{ p.name }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.type-filter {
  padding: 10px 12px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
}

.filter-header {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.filter-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.filter-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 12px;
  transition: all 0.15s;
  user-select: none;
}

.filter-chip input {
  display: none;
}

.filter-chip.checked {
  border-color: var(--accent);
  background: #B5503C0D;
}

.chip-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.chip-text {
  color: var(--text-secondary);
}

.filter-chip.checked .chip-text {
  color: var(--accent);
}

.presets {
  display: flex;
  align-items: center;
  gap: 4px;
}

.preset-label {
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.preset-btn {
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-panel);
  font-size: 11px;
  font-family: inherit;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.preset-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}
</style>
