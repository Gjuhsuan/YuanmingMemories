<script setup lang="ts">
/**
 * GraphRAG 动态步骤可视化。
 * 步骤可被反思打回重新激活，支持多轮迭代展示。
 */
import { computed } from 'vue'

export interface StepState {
  id: string
  label: string
  icon: string
  status: 'pending' | 'active' | 'done' | 'retry'
  detail: string
  meta?: string
}

const props = defineProps<{ steps: StepState[] }>()

// 只显示非 pending 步骤 + 最近一个 pending（作为即将到来的占位）
const visibleSteps = computed(() => {
  const lastIdx = props.steps.length - 1
  return props.steps.filter((s, i) => {
    if (s.status !== 'pending') return true
    // 只保留最后一个 pending 之后的 pending（即紧挨着的下一步）
    const nextSteps = props.steps.slice(i + 1)
    const hasActiveAfter = nextSteps.some(ns => ns.status === 'active' || ns.status === 'done')
    return !hasActiveAfter
  })
})
</script>

<template>
  <div class="grs-container">
    <div
      v-for="step in visibleSteps"
      :key="step.id"
      class="grs-step"
      :class="step.status"
    >
      <!-- 指示器 -->
      <div class="grs-indicator">
        <span v-if="step.status === 'done'" class="grs-check">✓</span>
        <span v-else-if="step.status === 'retry'" class="grs-retry">↻</span>
        <span v-else-if="step.status === 'active'" class="grs-spinner">
          <span class="spinner-dot"></span>
        </span>
        <span v-else class="grs-pending-icon">{{ step.icon }}</span>
      </div>

      <!-- 文本 -->
      <div class="grs-body">
        <div class="grs-line1">
          <span class="grs-label" :class="{ 'line-through': step.status === 'done' || step.status === 'retry' }">
            {{ step.label }}
          </span>
          <span v-if="step.meta" class="grs-meta">{{ step.meta }}</span>
        </div>
        <div
          v-if="(step.status === 'active' || step.status === 'retry') && step.detail"
          class="grs-detail"
        >
          {{ step.detail }}
        </div>
        <div v-if="step.status === 'done' && step.detail && step.id.startsWith('reflect')" class="grs-detail grs-done-detail">
          {{ step.detail }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.grs-container {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 12px 14px;
  background: var(--bg-canvas);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 14px;
}

.grs-step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  transition: all 0.3s ease;
}

.grs-step.pending { opacity: 0.3; }

.grs-step.active {
  background: var(--bg-subtle);
  opacity: 1;
}

.grs-step.retry {
  background: #FFF8E1;
  opacity: 1;
}

.grs-step.done { opacity: 0.6; }

/* 指示器 */
.grs-indicator {
  width: 20px; height: 20px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; font-size: 12px;
}
.grs-check { color: #4A9E6B; font-weight: 700; }
.grs-retry { color: #D4A017; font-weight: 700; font-size: 15px; }
.grs-pending-icon { font-size: 12px; opacity: 0.4; }

/* 旋转动画 */
.grs-spinner {
  width: 14px; height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: grs-spin 0.6s linear infinite;
}
@keyframes grs-spin { to { transform: rotate(360deg); } }

/* 文本 */
.grs-body { flex: 1; min-width: 0; }
.grs-line1 { display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }
.grs-label { font-size: 13px; color: var(--text-primary); transition: color 0.3s; }
.grs-label.line-through { text-decoration: line-through; color: var(--text-muted); }
.grs-meta { font-size: 11px; color: var(--text-muted); white-space: nowrap; }

.grs-detail {
  margin-top: 3px; font-size: 12px; color: var(--text-secondary);
  line-height: 1.6; animation: grs-fade 0.25s ease;
  max-height: 100px; overflow-y: auto; white-space: pre-wrap; word-break: break-all;
}
.grs-done-detail { color: var(--text-muted); font-style: italic; }

@keyframes grs-fade {
  from { opacity: 0; transform: translateY(-2px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
