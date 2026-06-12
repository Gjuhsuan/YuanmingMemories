<script setup lang="ts">
/**
 * G6 v5 画布。
 * - 样式变更（高亮切换）：setData + draw() → 无布局重算 → 位置不跳
 * - 数据变更（新增节点/边）：setData + render() → 跑布局
 * - 高亮切换后丝滑居中到选中节点：focusElement()
 */
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { Graph } from '@antv/g6'
import { base, state as cs } from '@/theme/palette'
import { truncateLabel } from '@/utils/size'

const props = defineProps<{
  nodes: any[]; edges: any[]; mode?: 'explore' | 'rag'
  highlightId?: string | null; citedIds?: string[]; loading?: boolean
}>()

const emit = defineEmits<{
  'node-click': [node: any]
  'add-context': [node: any]; 'empty-click': []
}>()

const container = ref<HTMLDivElement>()
const tooltip = ref({ show: false, x: 0, y: 0, text: '', sub: '' })
let graph: Graph | null = null
let _initialRender = true
let _currentHighlight: string | null = null
let _layoutDone = false  // 首次 render 后置 true，后续 highlight 切换只 draw

const nodeCache = ref<any[]>([])
const edgeCache = ref<any[]>([])
function getId(evt: any) { return evt.itemId || evt.target?.id || '' }

// 颜色加深：将 hex 颜色各通道乘以 factor（0.7 = 加深 30%）
function darken(hex: string, factor = 0.7): string {
  const c = hex.replace('#', '')
  const r = Math.round(parseInt(c.slice(0, 2), 16) * factor)
  const g = Math.round(parseInt(c.slice(2, 4), 16) * factor)
  const b = Math.round(parseInt(c.slice(4, 6), 16) * factor)
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`
}

// ── 构建带样式的 G6 数据 ──
function buildGraphData(highlightId: string | null) {
  const nodes = nodeCache.value
  const edges = edgeCache.value

  const neighborIds = new Set<string>()
  if (highlightId) {
    neighborIds.add(highlightId)
    edges.forEach((e: any) => {
      if (e.source === highlightId) neighborIds.add(e.target)
      if (e.target === highlightId) neighborIds.add(e.source)
    })
  }

  const gNodes = nodes.map((n: any) => {
    // 基础样式：描边使用节点颜色加深版
    const base = { size: n.size ?? 24, fill: n.color, stroke: darken(n.color, 0.7), lineWidth: 2 }
    if (!highlightId) {
      return { id: n.id, data: n, style: { ...base, opacity: 1, labelText: truncateLabel(n.name), labelFontSize: 12 } }
    }
    if (n.id === highlightId) {
      return { id: n.id, data: n, style: { ...base, opacity: 1, stroke: cs.selectedStroke, lineWidth: 3, labelText: truncateLabel(n.name), labelFontSize: 13 } }
    }
    if (neighborIds.has(n.id)) {
      return { id: n.id, data: n, style: { ...base, opacity: 0.9, labelText: truncateLabel(n.name), labelFontSize: 12 } }
    }
    return { id: n.id, data: n, style: { ...base, opacity: 0.1, labelText: '', labelFontSize: 10 } }
  })

  const gEdges = edges.map((e: any) => {
    if (!highlightId) {
      return { id: e.id, source: e.source, target: e.target, data: e, style: { stroke: base.edge, lineWidth: 1, opacity: 1, labelText: e.type_cn || '' } }
    }
    const isNeighbor = e.source === highlightId || e.target === highlightId
    return {
      id: e.id, source: e.source, target: e.target, data: e,
      style: { stroke: isNeighbor ? cs.selectedStroke : base.edge, lineWidth: isNeighbor ? 1.5 : 0.5, opacity: isNeighbor ? 1 : 0.1, labelText: isNeighbor ? (e.type_cn || '') : '', labelFontSize: 10 },
    }
  })

  if (props.citedIds?.length) {
    gNodes.forEach((gn: any) => {
      if (props.citedIds!.includes(gn.id)) {
        gn.style.stroke = cs.selectedStroke; gn.style.lineWidth = 2; gn.style.lineDash = [4, 2]
      }
    })
  }
  return { nodes: gNodes, edges: gEdges }
}

// ★ highlight-only：只改样式，不跑布局 → 位置不跳 + 丝滑居中
function renderHighlight(highlightId: string | null) {
  if (!graph) return
  _currentHighlight = highlightId
  const data = buildGraphData(highlightId)
  graph.setData(data)
  graph.draw()  // ← 只重绘，不重排！镜头位置保持完全不动
}

// ★ data-change（新增节点/边）：跑完整 layout
function renderWithLayout(highlightId: string | null, fitView = false) {
  if (!graph) return
  _currentHighlight = highlightId
  _layoutDone = true

  const savedZoom = _initialRender ? null : graph.getZoom()
  const data = buildGraphData(highlightId)
  graph.setData(data)
  graph.render().then(() => {
    if (_initialRender) {
      graph!.fitView({ padding: 60 }); _initialRender = false
    } else if (savedZoom != null && !fitView) {
      graph!.zoomTo(savedZoom)
    }
    if (fitView) graph!.fitView({ padding: 60 })
  })
}

// ── G6 初始化 ──
function initGraph() {
  if (!container.value) return
  const W = container.value.clientWidth, H = container.value.clientHeight

  graph = new Graph({
    container: container.value, width: W, height: H,
    autoFit: 'center', animation: false, background: base.bgCanvas,
    node: {
      type: 'circle',
      style: (d: any) => {
        const fill = d.style?.fill ?? d.data?.color ?? '#9A938A'
        return {
        size: d.style?.size ?? 24, fill,
        stroke: d.style?.stroke ?? darken(fill, 0.7), lineWidth: d.style?.lineWidth ?? 2,
        opacity: d.style?.opacity ?? 1, labelText: d.style?.labelText ?? '',
        labelFontSize: d.style?.labelFontSize ?? 12, labelFill: base.textPrimary,
        labelPlacement: 'bottom', labelOffsetY: 6, cursor: 'pointer', lineDash: d.style?.lineDash,
      }},
    },
    edge: {
      type: 'line',
      style: (d: any) => ({
        stroke: d.style?.stroke ?? base.edge, lineWidth: d.style?.lineWidth ?? 1,
        opacity: d.style?.opacity ?? 1,
        endArrow: { type: 'triangle', size: 8, fill: d.style?.stroke ?? base.edge },
        labelText: d.style?.labelText ?? '', labelFontSize: 10, labelFill: base.textSecondary,
        labelBackground: true, labelBackgroundFill: base.bgCanvas,
        labelBackgroundOpacity: 0.85, labelBackgroundPadding: [2, 4], labelOffsetY: -6,
      }),
    },
    layout: {
      type: 'd3-force',
      preventOverlap: true,
      nodeSize: 38,
      linkDistance: 280,
      nodeStrength: -500,
      edgeStrength: 0.3,
      collideStrength: 1.5,
      alphaDecay: 0.018,
      alphaMin: 0.002,
      alpha: 0.6,
      center: [W / 2, H / 2],
      gravity: 0.12,
    },
    behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element'],
  })

  graph.on('node:click', (evt: any) => {
    const nid = getId(evt); if (!nid) return
    const nd = nodeCache.value.find((n: any) => n.id === nid)
    if (nd) emit('node-click', nd)
  })
  graph.on('canvas:click', () => { tooltip.value.show = false; emit('empty-click') })

  graph.on('node:pointerenter', (evt: any) => {
    const nid = getId(evt); if (!nid) return
    const nd = nodeCache.value.find((n: any) => n.id === nid)
    if (nd) tooltip.value = { show: true, x: evt.client?.x ?? evt.clientX ?? 0, y: (evt.client?.y ?? evt.clientY ?? 0) - 50, text: nd.name, sub: `${nd.type_cn}${nd.subtype_cn ? ' · ' + nd.subtype_cn : ''}${nd.date_text ? ' · ' + nd.date_text : ''}  度数: ${nd.degree}` }
  })
  graph.on('node:pointermove', (evt: any) => {
    if (!tooltip.value.show) return
    tooltip.value.x = evt.client?.x ?? evt.clientX ?? tooltip.value.x
    tooltip.value.y = (evt.client?.y ?? evt.clientY ?? 0) - 50
  })
  graph.on('node:pointerleave', () => { tooltip.value.show = false })
  graph.on('edge:pointerenter', (evt: any) => {
    const eid = getId(evt); if (!eid) return
    const ed = edgeCache.value.find((e: any) => e.id === eid)
    if (ed) tooltip.value = { show: true, x: evt.client?.x ?? evt.clientX ?? 0, y: (evt.client?.y ?? evt.clientY ?? 0) - 40, text: ed.type_cn || ed.type || '', sub: ed.evidence || '' }
  })
  graph.on('edge:pointermove', (evt: any) => {
    if (!tooltip.value.show) return
    tooltip.value.x = evt.client?.x ?? evt.clientX ?? tooltip.value.x
    tooltip.value.y = (evt.client?.y ?? evt.clientY ?? 0) - 40
  })
  graph.on('edge:pointerleave', () => { tooltip.value.show = false })

  renderWithLayout(null, true)
}

// ── 数据变更 → 跑 layout ──
watch([() => props.nodes, () => props.edges], ([nn, ne], [on, oe]) => {
  nodeCache.value = nn || []; edgeCache.value = ne || []
  if (!graph) return
  // 数据引用变化就重新渲染（not just count change）
  if (nn !== on || ne !== oe) {
    renderWithLayout(_currentHighlight, false)
  }
})

// ★ highlightId 变更 → 只 draw，不 layout；丝滑居中
watch(() => props.highlightId, (newId) => {
  if (!graph) return
  renderHighlight(newId || null)
})

watch(() => props.citedIds, () => {
  if (!graph || !props.citedIds?.length) return
  if (_layoutDone) renderHighlight(_currentHighlight)
  else renderWithLayout(_currentHighlight, false)
}, { deep: true })

function changeLayout(type: string) {
  if (!graph) return
  if (type === 'd3-force') {
    const W = container.value?.clientWidth || 800
    const H = container.value?.clientHeight || 600
    graph.setLayout({
      type: 'd3-force',
      preventOverlap: true,
      nodeSize: 38,
      linkDistance: 280,
      nodeStrength: -500,
      edgeStrength: 0.3,
      collideStrength: 1.5,
      alphaDecay: 0.018,
      alphaMin: 0.002,
      alpha: 0.6,
      center: [W / 2, H / 2],
      gravity: 0.12,
    })
  } else if (type === 'radial') {
    graph.setLayout({
      type: 'radial',
      unitRadius: 150,
      linkDistance: 200,
      preventOverlap: true,
      nodeSize: 45,
      strictRadial: false,
    })
  } else if (type === 'dagre') {
    graph.setLayout({
      type: 'dagre',
      rankdir: 'TB',
      nodesep: 50,
      ranksep: 100,
    })
  }
  graph.render()
}
function fitView()  { graph?.fitView({ padding: 60 }) }
function resetView() { graph?.fitView({ padding: 60 }) }

onMounted(() => { nodeCache.value = props.nodes; edgeCache.value = props.edges; nextTick(() => initGraph()) })
onUnmounted(() => { graph?.destroy(); graph = null })
defineExpose({ changeLayout, fitView, resetView })
</script>

<template>
  <div class="graph-canvas-wrapper">
    <div ref="container" class="graph-container"></div>
    <div v-if="tooltip.show" class="graph-tooltip" :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }">
      <div class="tooltip-title">{{ tooltip.text }}</div>
      <div v-if="tooltip.sub" class="tooltip-sub">{{ tooltip.sub }}</div>
    </div>
    <div v-if="loading" class="loading-bar"><div class="loading-bar-inner"></div></div>
    <div class="graph-toolbar">
      <button @click="fitView">⊞</button><button @click="resetView">↺</button>
      <select @change="changeLayout(($event.target as HTMLSelectElement).value)">
        <option value="d3-force">力导向</option><option value="radial">辐射状</option><option value="dagre">层次</option>
      </select>
    </div>
    <div v-if="!loading && (!nodes || nodes.length === 0)" class="empty-state">
      <div class="empty-icon">◉</div><p>暂无图谱数据</p><p class="empty-sub">请调整筛选条件或搜索关键词</p>
    </div>
  </div>
</template>

<style scoped>
.graph-canvas-wrapper { position:relative; width:100%; height:100%; background:var(--bg-canvas); }
.graph-container { width:100%; height:100%; }
.graph-tooltip { position:fixed; z-index:100; pointer-events:none; background:var(--bg-panel); border:1px solid var(--border); border-radius:var(--radius-sm); padding:6px 10px; box-shadow:var(--shadow-sm); max-width:320px; transform:translate(-50%,-100%); }
.tooltip-title { font-size:13px; font-weight:500; color:var(--text-primary); line-height:1.4; }
.tooltip-sub { font-size:11px; color:var(--text-secondary); margin-top:2px; line-height:1.4; }
.loading-bar { position:absolute; top:0; left:0; right:0; height:2px; background:var(--border); overflow:hidden; z-index:10; }
.loading-bar-inner { height:100%; width:30%; background:var(--accent); animation:loading-slide 1.2s ease-in-out infinite; }
@keyframes loading-slide { 0%{transform:translateX(-100%)} 100%{transform:translateX(400%)} }
.graph-toolbar { position:absolute; bottom:12px; left:12px; display:flex; gap:6px; background:var(--bg-panel); border:1px solid var(--border); border-radius:var(--radius-sm); padding:4px; box-shadow:var(--shadow-sm); z-index:10; }
.graph-toolbar button, .graph-toolbar select { padding:4px 8px; border:1px solid transparent; border-radius:var(--radius-sm); font-size:13px; font-family:inherit; background:none; color:var(--text-secondary); cursor:pointer; transition:all .15s; }
.graph-toolbar button:hover, .graph-toolbar select:hover { background:var(--bg-subtle); color:var(--text-primary); }
.empty-state { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; pointer-events:none; color:var(--text-muted); }
.empty-icon { font-size:40px; margin-bottom:12px; opacity:.5; }
.empty-state p { font-size:15px; margin-bottom:4px; }
.empty-sub { font-size:13px!important; color:var(--text-muted); }
</style>
