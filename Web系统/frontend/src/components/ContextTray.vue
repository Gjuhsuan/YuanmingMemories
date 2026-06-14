<script setup lang="ts">
import { useContextStore } from '@/stores/context'

const context = useContextStore()

function remove(id: string) {
  context.removeItem(id)
}
</script>

<template>
  <div class="context-tray">
    <div class="tray-header">
      <h3>AI 上下文篮</h3>
      <span class="tray-count">{{ context.count }}/12</span>
    </div>

    <div class="tray-body">
      <p v-if="context.items.length === 0" class="tray-empty">
        尚未添加节点。<br>在图谱中点击节点可加入上下文篮，<br>AI 回答时将参考这些节点。
      </p>

      <div v-for="item in context.items" :key="item.id" class="tray-chip">
        <span class="chip-dot" :style="{ background: item.color }"></span>
        <span class="chip-name">{{ item.name }}</span>
        <span class="chip-type" :style="{ color: item.color }">{{ item.type_cn }}</span>
        <span class="chip-from">{{ item.addedFrom === 'explore' ? '探索' : '问答' }}</span>
        <button class="chip-remove" @click="remove(item.id)" title="移除">✕</button>
      </div>
    </div>

    <div class="tray-footer">
      <button
        class="btn-clear"
        :disabled="context.items.length === 0"
        @click="context.clear()"
      >
        清空
      </button>
    </div>
  </div>
</template>

<style scoped>
.context-tray {
  position: absolute;
  top: 8px;
  right: 12px;
  z-index: 100;
  width: 340px;
  max-height: 480px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
  z-index: 45;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.tray-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}

.tray-header h3 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.tray-count {
  font-size: 12px;
  color: var(--text-secondary);
}

.tray-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.tray-empty {
  padding: 32px 16px;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.8;
}

.tray-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  background: var(--bg-subtle);
  margin-bottom: 4px;
  font-size: 13px;
}

.chip-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.chip-name {
  flex: 1;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip-type {
  font-size: 11px;
  flex-shrink: 0;
}

.chip-from {
  font-size: 10px;
  color: var(--text-muted);
  background: var(--bg-panel);
  padding: 1px 5px;
  border-radius: 2px;
  flex-shrink: 0;
}

.chip-remove {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-muted);
  padding: 2px;
  flex-shrink: 0;
  transition: color 0.15s;
}

.chip-remove:hover {
  color: var(--accent);
}

.tray-footer {
  padding: 8px 16px;
  border-top: 1px solid var(--border);
}

.btn-clear {
  width: 100%;
  padding: 6px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-panel);
  font-size: 13px;
  font-family: inherit;
  color: var(--text-secondary);
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.btn-clear:hover:not(:disabled) {
  color: var(--accent);
  border-color: var(--accent);
}

.btn-clear:disabled {
  opacity: 0.4;
  cursor: default;
}
</style>
