<script setup lang="ts">
/**
 * 页面①：三栏图谱探索
 *
 * Fix3: 双击节点 → 以该节点为中心拉取所有类型邻居
 * Fix5: 首次加载用预加载缓存，切换路由不重新加载
 */
import { ref, onMounted, computed } from 'vue'
import { useGraphStore } from '@/stores/graph'
import { useContextStore } from '@/stores/context'
import TopBar from '@/components/TopBar.vue'
import TypeFilter from '@/components/TypeFilter.vue'
import GraphCanvas from '@/components/GraphCanvas.vue'
import LeftArchive from '@/components/LeftArchive.vue'
import RightDashboard from '@/components/RightDashboard.vue'
import { nodeColors } from '@/theme/palette'
import { fetchPreload } from '@/api'

const graph = useGraphStore()
const context = useContextStore()

const canvasRef = ref<InstanceType<typeof GraphCanvas>>()
const leftCollapsed = ref(false)
const rightCollapsed = ref(false)
const showTypeFilter = ref(false)

const selectedTypes = computed(() => graph.filters.types)

const viewStats = computed(() => ({
  nodes: graph.nodes.length,
  edges: graph.edges.length,
}))

// Fix5: 首次加载用预加载数据，如果已有数据则跳过
onMounted(async () => {
  await graph.loadMeta()

  // 已有数据则跳过（如从 /chat 切回来）
  if (graph.nodes.length > 0) return

  // 尝试预加载（快速首屏）
  try {
    const preload = await fetchPreload()
    if (preload?.nodes?.length) {
      graph.nodes = preload.nodes
      graph.edges = preload.edges || []
      return
    }
  } catch { /* fall through to normal load */ }

  // 正常加载
  await graph.loadGraph()
})

// 搜索选中 → 以该节点为中心加载邻域图
async function onSearchSelect(id: string) {
  await onCenterNode(id)
}

// 节点单击：只选中查看信息，不重新加载图谱
async function onNodeClick(node: any) {
  if (node.id === graph.selectedId) {
    // 点击已选中节点 → 取消选中
    graph.clearSelection()
    return
  }
  await graph.selectNode(node.id)    // 选中 + 右侧显示详情
}

// 以某节点为中心重新加载图谱（搜索选中 / 详情面板按钮）
async function onCenterNode(id: string) {
  await graph.loadGraph({
    types: Object.keys(nodeColors),
    limit: 200,
    centerId: id,
    hops: 1,
    degreeMode: graph.filters.degreeMode,
  })
  await graph.selectNode(id)
}

// 空白点击 → 取消选中
function onEmptyClick() {
  graph.clearSelection()
}

// 加入上下文
function addToContext(node: any) {
  context.addItem({
    id: node.id,
    idKind: node.idKind || 'entity',
    name: node.name,
    label: node.label,
    type_cn: node.type_cn,
    color: nodeColors[node.label] || '#9A938A',
    addedFrom: 'explore',
  })
}

// 类型筛选
function onTypeChange(selected: string[]) {
  graph.filters.types = selected
  graph.loadGraph({ types: selected })
}

function onTypePreset(name: string) {
  const presets: Record<string, string[]> = {
    '仅事件': ['Event'],
    '事件+人物': ['Event', 'Person'],
    '事件+地点': ['Event', 'Place'],
    '全部': Object.keys(nodeColors),
  }
  const types = presets[name] || Object.keys(nodeColors)
  graph.filters.types = types
  graph.loadGraph({ types })
}

// Cypher 执行
async function onCypherExecute(query: string, mode: 'replace' | 'append') {
  try {
    const res = await graph.runCypher(query)
    if (res.graph?.nodes?.length) {
      if (mode === 'replace') {
        graph.nodes = res.graph.nodes
        graph.edges = res.graph.edges || []
      } else {
        const existingIds = new Set(graph.nodes.map((n) => n.id))
        for (const n of res.graph.nodes) {
          if (!existingIds.has(n.id)) {
            graph.nodes.push(n)
            existingIds.add(n.id)
          }
        }
        const existingEdges = new Set(graph.edges.map((e) => e.id))
        for (const e of (res.graph.edges || [])) {
          if (!existingEdges.has(e.id)) {
            graph.edges.push(e)
            existingEdges.add(e.id)
          }
        }
      }
    }
    if (res.table) {
      alert(`查询返回 ${res.meta?.rowCount || 0} 行结果，耗时 ${res.meta?.tookMs || 0}ms`)
    }
  } catch (err: any) {
    alert(`Cypher 查询错误：${err.response?.data?.detail?.error?.message || err.message}`)
  }
}

// 看板定位
async function onLocateNode(id: string) {
  await graph.selectNode(id)
}
</script>

<template>
  <div class="explore-page">
    <TopBar
      @search-select="onSearchSelect"
      @cypher-execute="onCypherExecute"
    />

    <div class="explore-body">
      <LeftArchive
        :detail="graph.nodeDetail"
        :loading="graph.loading"
        @add-context="addToContext"
        @locate="onLocateNode"
        @center="onCenterNode"
      />

      <div class="canvas-area">
        <GraphCanvas
          ref="canvasRef"
          :nodes="graph.nodes"
          :edges="graph.edges"
          mode="explore"
          :highlight-id="graph.selectedId"
          :loading="graph.loading"
          @node-click="onNodeClick"
          @add-context="addToContext"
          @empty-click="onEmptyClick"
        />

        <div class="type-filter-overlay">
          <button class="filter-toggle" @click="showTypeFilter = !showTypeFilter">
            筛选 ▾
          </button>
          <TypeFilter
            v-if="showTypeFilter"
            :types="Object.keys(nodeColors)"
            :selected="graph.filters.types"
            :meta="graph.meta"
            @change="onTypeChange"
            @preset="onTypePreset"
          />
        </div>

        <div class="limit-control">
          <select
            :value="graph.filters.limit"
            @change="graph.loadGraph({ limit: Number(($event.target as HTMLSelectElement).value) })"
            title="节点上限"
          >
            <option :value="100">100 节点</option>
            <option :value="300">300 节点</option>
            <option :value="500">500 节点</option>
            <option :value="800">800 节点</option>
          </select>
          <span v-if="graph.truncated" class="truncated-badge">
            已截断（{{ graph.totalCandidates }} 候选）
          </span>
        </div>
      </div>

      <RightDashboard
        :view-node-count="viewStats.nodes"
        :view-edge-count="viewStats.edges"
        :truncated="graph.truncated"
        :total-candidates="graph.totalCandidates"
        @toggle-type="onTypeChange([...graph.filters.types.includes($event) ? graph.filters.types.filter(t => t !== $event) : [...graph.filters.types, $event]])"
        @locate="onLocateNode"
      />
    </div>
  </div>
</template>

<style scoped>
.explore-page { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.explore-body { display: flex; flex: 1; overflow: hidden; }
.canvas-area { flex: 1; position: relative; overflow: hidden; }
.type-filter-overlay { position: absolute; top: 12px; left: 12px; z-index: 20; display: flex; flex-direction: column; gap: 6px; }
.filter-toggle {
  padding: 5px 12px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--bg-panel); font-size: 13px; font-family: inherit;
  color: var(--text-secondary); cursor: pointer; box-shadow: var(--shadow-sm);
}
.filter-toggle:hover { color: var(--accent); border-color: var(--accent); }
.limit-control { position: absolute; bottom: 12px; right: 12px; display: flex; align-items: center; gap: 8px; z-index: 20; }
.limit-control select {
  padding: 4px 8px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--bg-panel); font-size: 12px; font-family: inherit; color: var(--text-secondary);
  box-shadow: var(--shadow-sm);
}
.truncated-badge {
  font-size: 11px; color: var(--accent); background: var(--bg-panel);
  padding: 3px 8px; border-radius: var(--radius-sm); border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}
</style>
