<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { fetchDashboard } from '@/api'
import { nodeColors } from '@/theme/palette'

const props = defineProps<{
  viewNodeCount?: number
  viewEdgeCount?: number
  truncated?: boolean
  totalCandidates?: number
}>()

const emit = defineEmits<{
  'toggle-type': [label: string]
  'locate': [id: string]
}>()

const dashboard = ref<any>(null)
const eventColor = nodeColors.Event

onMounted(async () => {
  try {
    dashboard.value = await fetchDashboard()
  } catch { /* ignore */ }
})

const maxSubtype = computed(() => {
  if (!dashboard.value?.eventSubtypes?.length) return 1
  return Math.max(...dashboard.value.eventSubtypes.map((s: any) => s.count))
})
</script>

<template>
  <aside class="right-dashboard">
    <div class="db-content">
      <h3 class="db-title">数据看板</h3>

      <!-- 图例 -->
      <section class="db-section">
        <h4>图例</h4>
        <div
          v-for="nt in dashboard?.nodeCounts"
          :key="nt.label"
          class="legend-row"
          :class="{ primary: nt.label === 'Event' }"
          @click="emit('toggle-type', nt.label)"
        >
          <span class="legend-dot" :style="{ background: nt.color }"></span>
          <span class="legend-label">{{ nt.cn }}</span>
          <span class="legend-count">{{ nt.count }}</span>
          <span v-if="nt.label === 'Event'" class="legend-focus">焦点</span>
        </div>
      </section>

      <!-- 概览统计 -->
      <section class="db-section">
        <h4>概览统计</h4>
        <div class="stat-grid">
          <div class="stat-item">
            <div class="stat-val">{{ dashboard?.totals?.nodes ?? '-' }}</div>
            <div class="stat-label">节点总数</div>
          </div>
          <div class="stat-item">
            <div class="stat-val">{{ dashboard?.totals?.edges ?? '-' }}</div>
            <div class="stat-label">关系总数</div>
          </div>
          <div class="stat-item">
            <div class="stat-val">{{ props.viewNodeCount ?? '-' }}</div>
            <div class="stat-label">当前视图</div>
          </div>
        </div>
        <p v-if="props.truncated" class="truncated-hint">
          （已截断，共 {{ props.totalCandidates }} 候选节点）
        </p>
      </section>

      <!-- 重要节点 Top 10 -->
      <section class="db-section">
        <h4>重要节点 Top 10</h4>
        <p class="db-method">（{{ dashboard?.importanceMethod || '度中心性' }}）</p>
        <div
          v-for="(item, i) in dashboard?.topNodes"
          :key="item.id"
          class="top-row"
          @click="emit('locate', item.id)"
        >
          <span class="top-rank">{{ i + 1 }}</span>
          <span class="top-dot" :style="{ background: item.color }"></span>
          <span class="top-name">{{ item.name }}</span>
          <span class="top-val">{{ item.degree }}</span>
        </div>
      </section>

      <!-- 事件类型分布 -->
      <section class="db-section">
        <h4>事件类型分布</h4>
        <div
          v-for="st in dashboard?.eventSubtypes"
          :key="st.cn"
          class="bar-row"
        >
          <span class="bar-label">{{ st.cn }}</span>
          <div class="bar-track">
            <div
              class="bar-fill"
              :style="{
                width: (st.count / maxSubtype * 100) + '%',
                background: eventColor,
              }"
            ></div>
          </div>
          <span class="bar-val">{{ st.count }}</span>
        </div>
      </section>
    </div>
  </aside>
</template>

<style scoped>
.right-dashboard {
  width: 300px;
  background: var(--bg-panel);
  border-left: 1px solid var(--border);
  flex-shrink: 0;
  overflow-y: auto;
}

.db-content {
  padding: 20px;
}

.db-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 20px;
}

.db-section {
  margin-bottom: 24px;
}

.db-section h4 {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

/* 图例 */
.legend-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.1s;
}

.legend-row:hover {
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
}

.legend-row.primary {
  font-weight: 500;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-label {
  flex: 1;
  color: var(--text-primary);
}

.legend-count {
  font-size: 12px;
  color: var(--text-muted);
}

.legend-focus {
  font-size: 10px;
  color: var(--accent);
  background: #B5503C1A;
  padding: 1px 4px;
  border-radius: 2px;
}

/* 统计 */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.stat-item {
  text-align: center;
  padding: 10px 4px;
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
}

.stat-val {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  font-family: "Roboto Mono", monospace;
}

.stat-label {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}

.truncated-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 6px;
}

/* Top N */
.db-method {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.top-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 0;
  cursor: pointer;
  font-size: 12px;
  transition: background 0.1s;
}

.top-row:hover {
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
}

.top-rank {
  width: 18px;
  text-align: center;
  color: var(--text-muted);
  font-weight: 500;
  font-size: 11px;
}

.top-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.top-name {
  flex: 1;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.top-val {
  color: var(--text-muted);
  font-family: "Roboto Mono", monospace;
  font-size: 11px;
}

/* 条形 */
.bar-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.bar-label {
  width: 80px;
  font-size: 12px;
  color: var(--text-secondary);
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bar-track {
  flex: 1;
  height: 10px;
  background: var(--bg-subtle);
  border-radius: 5px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 5px;
  transition: width 0.3s ease-out;
}

.bar-val {
  width: 30px;
  font-size: 11px;
  color: var(--text-muted);
  text-align: right;
  font-family: "Roboto Mono", monospace;
}
</style>
