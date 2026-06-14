<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { useContextStore } from '@/stores/context'

const route = useRoute()
const router = useRouter()
const context = useContextStore()

const tabs = [
  { path: '/ontology', label: '本体结构' },
  { path: '/explore', label: '图谱探索' },
  { path: '/chat', label: 'AI 问答' },
]
</script>

<template>
  <header class="top-nav">
    <div class="nav-left">
      <h1 class="app-title">圆明园事件知识图谱</h1>
      <nav class="nav-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.path"
          class="nav-tab"
          :class="{ active: route.path.startsWith(tab.path) }"
          @click="router.push(tab.path)"
        >
          {{ tab.label }}
        </button>
      </nav>
    </div>
    <div class="nav-right">
      <button class="basket-btn" @click="context.toggle()" title="AI 上下文篮">
        <span class="basket-icon">🧺</span>
        <span v-if="context.count > 0" class="basket-badge">{{ context.count }}</span>
      </button>
    </div>
  </header>
</template>

<style scoped>
.top-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 24px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
  z-index: 50;
  flex-shrink: 0;
}

.nav-left {
  display: flex;
  align-items: center;
  gap: 32px;
}

.app-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.nav-tabs {
  display: flex;
  gap: 4px;
}

.nav-tab {
  background: none;
  border: none;
  padding: 6px 16px;
  font-size: 14px;
  font-family: inherit;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: color 0.15s, background 0.15s;
  border-bottom: 2px solid transparent;
}

.nav-tab:hover {
  color: var(--text-primary);
  background: var(--bg-subtle);
}

.nav-tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  font-weight: 500;
}

.nav-right {
  display: flex;
  align-items: center;
}

.basket-btn {
  position: relative;
  background: none;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 6px 12px;
  cursor: pointer;
  font-size: 18px;
  transition: border-color 0.15s;
}

.basket-btn:hover {
  border-color: var(--accent);
}

.basket-icon {
  display: block;
}

.basket-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  background: var(--accent);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  min-width: 18px;
  height: 18px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
}
</style>
